"""Security and correctness audit of Sentinel (M5) and video mode (M7)."""

import asyncio
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db
from app.main import app
from app.routers import sentinel as sentinel_router
from app.services import video_jobs
from app.services.video import VideoError

TOKEN = os.environ["SENTINEL_TOKEN"]
AUTH = {"X-Sentinel-Token": TOKEN}
LAT = 29.0  # this file's own test streets, far from other tests
A, B, C = [LAT, 93.0], [LAT + 0.002, 93.0], [LAT + 0.004, 93.0]
JPEG = b"\xff\xd8\xff\xe0" + b"1" * 2000


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    d = tmp_path_factory.mktemp("sec_videos")
    p = d / "sec_pattern.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=5", "-t", "32",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


@pytest.fixture
def env(tmp_path, monkeypatch, clip):
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "VIDEO_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "ASSET_VIDEO_DIR", clip.parent)
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 990001)).first():
            db.add_all([
                models.Street(osm_way_id=990001, name="Audit Rd", road_type="residential", road_class="residential",
                              start_node=990001, end_node=990002, length_m=222.4, geometry=[A, B]),
                models.Street(osm_way_id=990002, name="Audit Rd 2", road_type="residential", road_class="residential",
                              start_node=990002, end_node=990003, length_m=222.4, geometry=[B, C]),
            ])
            db.commit()
    with TestClient(app) as client:
        yield client, tmp_path


def photo(client, lat, device, headers=AUTH, speed=None, captured_at=None):
    data = {"lat": lat, "lon": 93.0, "accuracy_m": 8, "sentinel_label": "Audit #01", "device_id": device}
    if speed is not None:
        data["speed_kmh"] = speed
    if captured_at:
        data["captured_at"] = captured_at
    return client.post("/api/sentinel/photo", files={"image": ("p.jpg", JPEG, "image/jpeg")}, data=data, headers=headers)


def new_job(client, clip, waypoints=(A, C)):
    r = client.post("/api/sentinel/videos/jobs", headers=AUTH, json={
        "video_ref": f"asset:{clip.name}", "sentinel_label": "Audit #01", "waypoints": list(waypoints),
        "recorded_at_ist": "2026-10-29T23:00:00"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---- Finding: Sentinel endpoints had no access control (anyone on the network could write, delete, or read rider routes)

def test_sentinel_endpoints_require_the_access_code(env, clip):
    client, _ = env
    calls = [
        ("post", "/api/sentinel/photo", dict(files={"image": ("p.jpg", JPEG, "image/jpeg")},
                                           data={"lat": LAT, "lon": 93.0, "accuracy_m": 5, "sentinel_label": "x", "device_id": "dddd"})),
        ("post", "/api/sentinel/videos/uploads", dict(files={"file": ("a.mp4", b"x", "video/mp4")})),
        ("post", "/api/sentinel/videos/jobs", dict(json={})),
        ("get", "/api/sentinel/videos/jobs", {}),
        ("get", "/api/sentinel/videos/jobs/1", {}),
        ("delete", "/api/sentinel/videos/jobs/1", {}),
        ("get", "/api/sentinel/videos/assets", {}),
        ("get", f"/api/sentinel/videos/assets/{clip.name}", {}),
        ("post", "/api/sentinel/trace", dict(json={"waypoints": [A, C]})),
    ]
    for method, url, kw in calls:
        assert getattr(client, method)(url, **kw).status_code == 401, url
        assert getattr(client, method)(url, headers={"X-Sentinel-Token": "wrong"}, **kw).status_code == 403, url
    assert client.get("/api/sentinel/status").status_code == 200  # counts only, stays public
    assert client.get("/api/sentinel/videos/assets", headers=AUTH).status_code == 200


def test_access_code_missing_on_server_blocks_writes(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(config, "SENTINEL_TOKEN", "")
    r = client.get("/api/sentinel/videos/jobs", headers={"X-Sentinel-Token": ""})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "no_access_code"


# ---- Finding: night-time and movement rules were only enforced in the browser

def test_night_rule_enforced_by_server(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(config, "SENTINEL_ENFORCE_NIGHT", True)
    monkeypatch.setattr(sentinel_router, "now_ist", lambda: datetime(2026, 10, 30, 12, 0))
    r = photo(client, LAT + 0.0003, "night-device-1")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "outside_hours"
    t0 = datetime.now(UTC).replace(tzinfo=None)
    monkeypatch.setattr(sentinel_router, "now_ist", lambda: datetime(2026, 10, 30, 23, 0))
    assert photo(client, LAT + 0.0003, "night-device-1", captured_at=(t0 - timedelta(seconds=30)).isoformat() + "Z").status_code == 200
    monkeypatch.setattr(sentinel_router, "now_ist", lambda: datetime(2026, 10, 31, 5, 59))
    assert photo(client, LAT + 0.0010, "night-device-1", captured_at=t0.isoformat() + "Z").status_code == 200


def test_movement_rule_enforced_by_server(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(config, "SENTINEL_ENFORCE_MOVING", True)
    assert photo(client, LAT + 0.0003, "move-device-1").json()["detail"]["code"] == "not_moving"  # speed not sent
    assert photo(client, LAT + 0.0003, "move-device-1", speed=3).json()["detail"]["code"] == "not_moving"
    assert photo(client, LAT + 0.0003, "move-device-1", speed=20).status_code == 200


def test_impossible_jump_rejected(env):
    client, _ = env
    now = datetime.now(UTC).replace(tzinfo=None)
    assert photo(client, LAT + 0.0003, "jump-device-1", captured_at=(now - timedelta(seconds=10)).isoformat() + "Z").status_code == 200
    # 0.0034 deg (~380 m) in 10 s is ~137 km/h: allowed below the 150 km/h limit
    assert photo(client, LAT + 0.0037, "jump-device-1", captured_at=now.isoformat() + "Z").status_code == 200
    # straight back ~380 m in 2 s = ~680 km/h: not a real ride
    r = photo(client, LAT + 0.0003, "jump-device-1", captured_at=(now + timedelta(seconds=2)).isoformat() + "Z")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "gps_jump"
    # without the phone's own time (server receive times only) the speed is not judged: no false "jump"
    assert photo(client, LAT + 0.0020, "jump-device-2").status_code == 200
    assert photo(client, LAT + 0.0030, "jump-device-2").status_code == 200


# ---- Duplicate prevention under concurrent uploads

def test_concurrent_duplicate_uploads_save_only_one(env):
    async def burst():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=AUTH) as ac:
            data = {"lat": LAT + 0.0025, "lon": 93.0, "accuracy_m": 8, "sentinel_label": "Audit #01", "device_id": "burst-device"}
            return await asyncio.gather(*[
                ac.post("/api/sentinel/photo", files={"image": ("p.jpg", JPEG, "image/jpeg")}, data=data) for _ in range(8)
            ])

    codes = sorted(r.status_code for r in asyncio.run(burst()))
    assert codes.count(200) == 1 and codes.count(409) == 7
    with Session(engine) as db:
        assert len(db.scalars(select(models.Observation).where(models.Observation.device_id == "burst-device")).all()) == 1


# ---- Finding: a failed video job left frames and observations behind

def test_failed_job_leaves_nothing_behind(env, clip, monkeypatch):
    client, tmp = env
    job_id = new_job(client, clip)
    real = video_jobs.extract_frame
    calls = {"n": 0}

    def flaky(src, t, out):
        calls["n"] += 1
        if calls["n"] == 4:
            out.write_bytes(b"")  # half-written file, like a crashed FFmpeg
            raise VideoError("frame_failed", "Could not read the frame.")
        real(src, t, out)

    monkeypatch.setattr(video_jobs, "extract_frame", flaky)
    video_jobs.process_job(job_id)
    job = client.get(f"/api/sentinel/videos/jobs/{job_id}", headers=AUTH).json()
    assert job["status"] == "failed" and job["frames_done"] == 0
    with Session(engine) as db:
        assert db.scalars(select(models.Observation).where(models.Observation.video_job_id == job_id)).all() == []
    assert list((tmp / "photos").glob(f"video{job_id}_*")) == []


# ---- Database consistency after deleting a job

def test_deleting_one_job_leaves_others_intact(env, clip):
    client, tmp = env
    keep, drop = new_job(client, clip), new_job(client, clip, (C, A))
    video_jobs.process_job(keep)
    video_jobs.process_job(drop)
    assert client.delete(f"/api/sentinel/videos/jobs/{drop}", headers=AUTH).json()["observations_removed"] == 6
    with Session(engine) as db:
        assert db.scalars(select(models.Observation).where(models.Observation.video_job_id == drop)).all() == []
        kept = db.scalars(select(models.Observation).where(models.Observation.video_job_id == keep)).all()
        assert len(kept) == 6 and all(os.path.exists(o.photo_path) for o in kept)
        assert db.get(models.VideoJob, drop) is None
    assert list((tmp / "photos").glob(f"video{drop}_*")) == []
    assert clip.exists()


# ---- Retention: uploaded source videos get a delete time; abandoned uploads are cleaned up

def test_upload_retention_and_orphan_cleanup(env, clip):
    client, tmp = env
    up = client.post("/api/sentinel/videos/uploads", headers=AUTH, files={"file": ("ride.mp4", clip.read_bytes(), "video/mp4")}).json()
    r = client.post("/api/sentinel/videos/jobs", headers=AUTH, json={
        "video_ref": up["video_ref"], "sentinel_label": "Audit #01", "waypoints": [A, C], "recorded_at_ist": "2026-10-29T23:00:00"})
    job_id = r.json()["id"]
    video_jobs.process_job(job_id)
    with Session(engine) as db:
        job = db.get(models.VideoJob, job_id)
        assert job.file_delete_at is not None
        assert timedelta(hours=5, minutes=59) < job.file_delete_at - job.finished_at <= timedelta(hours=6, seconds=5)

    orphan = tmp / "uploads" / "upload_aaaaaaaaaaaa__old.mp4"
    orphan.write_bytes(b"old")
    old = time.time() - 25 * 3600
    os.utime(orphan, (old, old))
    fresh = tmp / "uploads" / "upload_bbbbbbbbbbbb__new.mp4"
    fresh.write_bytes(b"new")
    removed = video_jobs.cleanup_orphan_uploads()
    assert orphan.name in removed and not orphan.exists()
    assert fresh.exists()  # may still be about to become a job
    assert (tmp / "uploads" / up["video_ref"].split(":", 1)[1]).exists()  # belongs to a job: kept
