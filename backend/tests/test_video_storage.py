"""Sentinel video storage (agreed: 1 GB Render disk, 250 MB per video): upload limit enforced while the upload arrives,
nothing left behind after a rejected or failed upload / job, disk reserve respected, orphan cleanup that never touches
active jobs or kept media, repeated runs and restarts. Generated test clips only; isolated database and folders."""

import os
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.main import app
from app.services import retention, storage, video_jobs
from app.services import walk_monitor as monitor_module
from app.services.geo import line_length_m

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
AUTH = {"X-Sentinel-Token": os.environ["SENTINEL_TOKEN"]}
LAT, LON = 56.0, 116.0
A, C = [LAT, LON], [LAT + 0.004, LON]  # ~445 m straight north


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    p = tmp_path_factory.mktemp("clips") / "storage_test.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10", "-t", "12",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "REDACTED_DIR", tmp_path / "photos" / "redacted")
    monkeypatch.setattr(config, "VIDEO_DIR", tmp_path / "uploads")
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 880601)).first():
            db.add_all([models.Street(osm_way_id=880601 + i, name="Storage Test Rd", road_type="residential", road_class="residential",
                                      start_node=880601 + i, end_node=880602 + i, length_m=line_length_m(g), geometry=g, city="guwahati")
                        for i, g in enumerate([[A, [LAT + 0.002, LON]], [[LAT + 0.002, LON], C]])])
            db.commit()
    with TestClient(app) as c:
        yield c, tmp_path


def upload(c, path, headers=AUTH):
    with open(path, "rb") as f:
        return c.post("/api/sentinel/videos/uploads", files={"file": (path.name, f, "video/mp4")}, headers=headers)


def uploads_on_disk():
    return sorted(config.VIDEO_DIR.glob("*")) if config.VIDEO_DIR.is_dir() else []


def make_job(c, clip):
    ref = upload(c, clip).json()["video_ref"]
    r = c.post("/api/sentinel/videos/jobs", headers=AUTH, json={"video_ref": ref, "sentinel_label": "Storage test", "waypoints": [A, C],
                                                               "recorded_at_ist": "2026-10-29T23:00:00", "frame_interval_s": 2})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def job_state(job_id):
    with SessionLocal() as db:
        j = db.get(models.VideoJob, job_id)
        n = db.scalar(select(func.count()).select_from(models.Observation).where(models.Observation.video_job_id == job_id))
        return j.status, j.error, n, j.file_delete_at, j.file_path


def age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


# ---------------- The configured limit ----------------

def test_agreed_limits_are_configured_consistently():
    assert config.MAX_VIDEO_UPLOAD_MB == 250 and config.MAX_VIDEO_UPLOAD_BYTES == 250 * 1024 * 1024
    render = (ROOT / "render.yaml").read_text()
    assert "sizeGB: 1" in render and 'key: MAX_VIDEO_UPLOAD_MB\n        value: "250"' in render
    assert "250 MB" in (ROOT / "docs" / "DEPLOYMENT.md").read_text()


# ---------------- Upload size: below, exactly at and above the limit ----------------

def test_upload_below_and_exactly_at_the_limit_is_accepted(env, clip, monkeypatch):
    c, _ = env
    size = clip.stat().st_size
    for limit in (size + 1, size):
        monkeypatch.setattr(config, "MAX_VIDEO_UPLOAD_BYTES", limit)
        r = upload(c, clip)
        assert r.status_code == 200, (limit, r.text)
        assert (config.VIDEO_DIR / r.json()["video_ref"].split(":", 1)[1]).stat().st_size == size


def test_upload_one_byte_over_the_limit_is_refused_and_nothing_is_kept(env, clip, monkeypatch):
    c, _ = env
    monkeypatch.setattr(config, "MAX_VIDEO_UPLOAD_BYTES", clip.stat().st_size - 1)
    r = upload(c, clip)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert "MB are not supported" in r.json()["detail"]["message"]
    assert uploads_on_disk() == []  # the partly written copy was removed


def test_announced_size_over_the_limit_is_refused_before_reading(env, clip, monkeypatch):
    c, _ = env
    monkeypatch.setattr(config, "MAX_VIDEO_UPLOAD_BYTES", 1000)  # the clip is far larger than 1000 B + form allowance
    called = []
    monkeypatch.setattr("app.routers.sentinel.probe", lambda p: called.append(p))
    r = upload(c, clip)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert called == [] and uploads_on_disk() == []  # the endpoint never ran


def test_access_code_is_checked_before_the_video_is_read(env, clip):
    c, _ = env
    assert upload(c, clip, headers={}).status_code == 401
    assert upload(c, clip, headers={"X-Sentinel-Token": "wrong"}).status_code == 403
    assert uploads_on_disk() == []


def test_not_enough_disk_space_refuses_the_upload(env, clip, monkeypatch):
    c, _ = env
    monkeypatch.setattr(storage, "free_bytes", lambda path=None: storage.reserve_bytes() + 1000)
    r = upload(c, clip)
    assert r.status_code == 507 and r.json()["detail"]["code"] == "disk_full"
    assert uploads_on_disk() == []


def test_failure_while_saving_removes_the_partial_file(env, clip, monkeypatch):
    c, _ = env
    calls = []

    def room(needed):  # the guard's check passes, then the disk "fills up" while the file is being copied
        calls.append(needed)
        return len(calls) < 2
    monkeypatch.setattr(storage, "has_room", room)
    big = clip.parent / "storage_big.mp4"
    big.write_bytes(clip.read_bytes() * 30)  # several 1 MB chunks
    r = upload(c, big)
    assert r.status_code == 507 and uploads_on_disk() == []


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_streamed_upload_without_size_is_stopped_at_the_limit(tmp_path):
    """A real server with a 1 MB limit receives a 6 MB upload sent in chunks without a declared size."""
    port, data = _free_port(), tmp_path / "data"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 's.db'}", "DATA_DIR": str(data), "START_WORKERS": "0",
           "MAX_VIDEO_UPLOAD_MB": "1", "SENTINEL_TOKEN": "stream-code", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    sent = 0
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        boundary = "shadowmapboundary"

        def body():
            nonlocal sent
            yield (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"ride.mp4\"\r\n"
                   "Content-Type: video/mp4\r\n\r\n").encode()
            for _ in range(24):  # 24 x 256 KB = 6 MB
                sent += 256 * 1024
                yield b"\0" * (256 * 1024)
            yield f"\r\n--{boundary}--\r\n".encode()
        try:
            r = httpx.post(f"{base}/api/sentinel/videos/uploads", content=body(), timeout=30,
                           headers={"X-Sentinel-Token": "stream-code", "Content-Type": f"multipart/form-data; boundary={boundary}"})
            status = r.status_code
            detail = r.json()["detail"]["code"]
        except httpx.HTTPError:  # the server may close the connection after answering
            status, detail = None, None
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=20)
    assert '"POST /api/sentinel/videos/uploads HTTP/1.1" 413' in out, out[-2000:]
    if status is not None:
        assert status == 413 and detail == "too_large"
    videos = data / "videos"
    assert not videos.exists() or list(videos.iterdir()) == []  # nothing was written to the data disk


# ---------------- Processing never exhausts the disk ----------------

def test_processing_refused_up_front_when_frames_would_not_fit(env, clip, monkeypatch):
    c, _ = env
    job = make_job(c, clip)
    monkeypatch.setattr(storage, "free_bytes", lambda path=None: storage.reserve_bytes() + config.FRAME_STORAGE_BYTES)  # room for 1 frame
    video_jobs.process_job(job)
    status, error, frames, delete_at, _ = job_state(job)
    assert status == "failed" and "Not enough storage space" in error and frames == 0
    assert delete_at is not None  # the uploaded copy is removed later by the normal 6-hour rule
    assert list(config.PHOTO_DIR.glob(f"video{job}_f*.jpg")) == []


def test_disk_filling_up_during_processing_stops_and_cleans_up(env, clip, monkeypatch):
    c, _ = env
    job = make_job(c, clip)
    real, calls = storage.free_bytes, []

    def shrinking(path=None):
        calls.append(1)
        return real(path) if len(calls) <= 3 else storage.reserve_bytes()  # fine at first, then full
    monkeypatch.setattr(storage, "free_bytes", shrinking)
    video_jobs.process_job(job)
    status, error, frames, _, _ = job_state(job)
    assert status == "failed" and "Not enough storage space" in error
    assert frames == 0 and list(config.PHOTO_DIR.glob(f"video{job}_f*.jpg")) == []  # nothing half-done kept


def test_normal_processing_still_works(env, clip):
    c, _ = env
    job = make_job(c, clip)
    video_jobs.process_job(job)
    status, error, frames, _, _ = job_state(job)
    assert status == "done" and error is None and frames == 6


# ---------------- Cleanup: orphans only, never active jobs or kept media ----------------

def test_cleanup_removes_only_orphans_and_protects_active_jobs_and_kept_media(env, clip):
    c, _ = env
    done = make_job(c, clip)
    video_jobs.process_job(done)
    queued = make_job(c, clip)  # waiting for the worker
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    orphan_upload = config.VIDEO_DIR / "upload_000000000000__abandoned.mp4"
    fresh_upload = config.VIDEO_DIR / "upload_111111111111__just_uploaded.mp4"
    orphan_frame = config.PHOTO_DIR / "video99999_f00000.jpg"  # job no longer exists, no observation
    queued_frame = config.PHOTO_DIR / f"video{queued}_f00000.jpg"  # being written by an active job
    for f in (orphan_upload, fresh_upload, orphan_frame, queued_frame):
        f.write_bytes(b"x" * 100)
    for f in (orphan_upload, orphan_frame, queued_frame):
        age(f, 3 * 3600)
    for f in config.VIDEO_DIR.glob("upload_*"):  # job uploads look old too: they must stay because jobs use them
        if f not in (orphan_upload, fresh_upload):
            age(f, 3 * 3600)
    kept_frames = sorted(config.PHOTO_DIR.glob(f"video{done}_f*.jpg"))
    for f in kept_frames:
        age(f, 3 * 3600)

    with SessionLocal() as db:
        removed = storage.cleanup_orphan_files(db)
    assert removed == {"uploads": 1, "frames": 1}
    assert not orphan_upload.exists() and not orphan_frame.exists()
    assert fresh_upload.exists() and queued_frame.exists()  # too new / active job
    assert all(f.exists() for f in kept_frames) and len(kept_frames) == 6  # observation media follow their own 6-hour rule
    for jid in (done, queued):
        assert Path(job_state(jid)[4]).exists()  # uploads used by jobs stay


def test_repeated_cleanup_is_harmless(env, clip):
    c, _ = env
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    orphan = config.VIDEO_DIR / "upload_222222222222__left.mp4"
    orphan.write_bytes(b"x")
    age(orphan, 3 * 3600)
    with SessionLocal() as db:
        first = retention.run(db, utcnow())
        second = retention.run(db, utcnow())
        third = retention.run(db, utcnow())
    assert first["orphan_files_removed"]["uploads"] == 1
    assert second["orphan_files_removed"] == third["orphan_files_removed"] == {"uploads": 0, "frames": 0}


def test_restart_requeues_interrupted_job_and_cleans_leftovers(env, clip, monkeypatch):
    c, _ = env
    job = make_job(c, clip)
    with SessionLocal() as db:  # the server stopped mid-way: job "processing", a half-written frame on disk
        db.get(models.VideoJob, job).status = "processing"
        db.commit()
    config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    half = config.PHOTO_DIR / f"video{job}_f00000.jpg"
    half.write_bytes(b"half")
    leftover = config.VIDEO_DIR / "upload_333333333333__crashed.mp4"
    leftover.write_bytes(b"partial")
    age(leftover, 3 * 3600)
    age(half, 3 * 3600)

    worker = video_jobs.VideoWorker()
    monkeypatch.setattr(worker._thread, "start", lambda: None)  # only the start-up recovery is under test
    worker.start()
    assert job_state(job)[0] == "queued"  # back in the queue
    assert half.exists()  # protected: its job is active again
    # the regular cleanup (first round of the background clock after start) removes the abandoned upload
    monkeypatch.setattr(monitor_module, "evaluate_all", lambda db, now: None)
    clock = monitor_module.WalkMonitor(every_s=0.05)
    clock.start()
    try:
        for _ in range(100):
            if not leftover.exists():
                break
            time.sleep(0.05)
    finally:
        clock.stop()
        clock._thread.join(timeout=10)  # no round may run after this test's patches are undone
    assert not leftover.exists() and half.exists()
    video_jobs.process_job(job)  # the requeued job runs again from the start and replaces the half frame
    status, _, frames, _, _ = job_state(job)
    assert status == "done" and frames == 6 and half.stat().st_size > 1000
