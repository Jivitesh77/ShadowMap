"""Sentinel live photos and the video pipeline, on generated test clips (never real footage or demo data)."""

import subprocess
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db
from app.main import app
from app.services import video_jobs
from app.services.geo import haversine_m
from app.services.video import VideoError, frame_times, probe

LAT = 28.0  # a test street far away from every other test's data
A, B, C = [LAT, 92.0], [LAT + 0.002, 92.0], [LAT + 0.004, 92.0]  # ~222 m apart, straight north
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A generated 32 s test pattern clip (not footage)."""
    d = tmp_path_factory.mktemp("videos")
    p = d / "test_pattern.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10", "-t", "32",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


@pytest.fixture
def env(tmp_path, monkeypatch, clip):
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "VIDEO_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "ASSET_VIDEO_DIR", clip.parent)
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 880001)).first():
            db.add_all([
                models.Street(osm_way_id=880001, name="Sentinel Test Rd", road_type="residential", road_class="residential",
                              start_node=880001, end_node=880002, length_m=222.4, geometry=[A, B]),
                models.Street(osm_way_id=880002, name="Sentinel Test Rd 2", road_type="residential", road_class="residential",
                              start_node=880002, end_node=880003, length_m=222.4, geometry=[B, C]),
            ])
            db.commit()
    with TestClient(app) as client:
        yield client, tmp_path


def test_probe_and_frame_times(clip, tmp_path):
    info = probe(clip)
    assert info["duration_s"] == 32 and info["width"] == 1280 and info["location_tag"] is None
    assert frame_times(32, 5) == [2.5, 7.5, 12.5, 17.5, 22.5, 27.5]
    assert frame_times(32, 5, start_s=10, end_s=20) == [12.5, 17.5]

    fake = tmp_path / "notes.mp4"
    fake.write_text("this is not a video")
    with pytest.raises(VideoError) as e:
        probe(fake)
    assert e.value.code == "unreadable"
    wrong = tmp_path / "slides.pptx"
    wrong.write_bytes(b"x")
    with pytest.raises(VideoError) as e:
        probe(wrong)
    assert e.value.code == "unsupported_format"
    audio = tmp_path / "audio_only.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=2", str(audio)], check=True)
    with pytest.raises(VideoError) as e:
        probe(audio)
    assert e.value.code == "no_video_stream"


def test_video_job_end_to_end(env, clip):
    client, tmp = env
    assets = client.get("/api/sentinel/videos/assets").json()["videos"]
    assert any(v["name"] == clip.name for v in assets)
    checked = client.get(f"/api/sentinel/videos/assets/{clip.name}").json()
    assert checked["info"]["creation_time_utc"] is None  # generated clip: no time stored, we never invent one

    no_time = client.post("/api/sentinel/videos/jobs", json={
        "video_ref": checked["video_ref"], "sentinel_label": "Test #01", "waypoints": [A, C], "use_video_time": True})
    assert no_time.status_code == 422 and no_time.json()["detail"]["code"] == "no_video_time"

    res = client.post("/api/sentinel/videos/jobs", json={
        "video_ref": checked["video_ref"], "sentinel_label": "Test #01", "waypoints": [A, C],
        "recorded_at_ist": "2026-10-29T23:00:00", "frame_interval_s": 5})
    assert res.status_code == 200, res.text
    job_id = res.json()["id"]
    assert res.json()["status"] == "queued" and 440 < res.json()["route_length_m"] < 450

    video_jobs.process_job(job_id)  # what the background worker does
    job = client.get(f"/api/sentinel/videos/jobs/{job_id}").json()
    assert job["status"] == "done" and job["frames_total"] == 6 and job["frames_done"] == 6
    assert job["analysis"] == {"pending": 6}
    assert {s["name"] for s in job["streets_covered"]} == {"Sentinel Test Rd", "Sentinel Test Rd 2"}

    with Session(engine) as db:
        obs = db.scalars(select(models.Observation).where(models.Observation.video_job_id == job_id)
                         .order_by(models.Observation.frame_time_s)).all()
    assert [o.frame_time_s for o in obs] == [2.5, 7.5, 12.5, 17.5, 22.5, 27.5]
    assert all(o.position_source == "traced_route" and o.gps_accuracy_m is None for o in obs)  # never claimed as GPS
    assert obs[0].captured_at == datetime(2026, 10, 29, 17, 30, 2, 500000)  # 23:00 IST = 17:30 UTC, + 2.5 s
    lats = [o.lat for o in obs]
    assert lats == sorted(lats)  # frames move forward along the traced route
    # steady speed: frame at 12.5 s of 32 s is 39% of the 444.8 m route
    assert haversine_m(A[0], A[1], obs[2].lat, obs[2].lon) == pytest.approx(12.5 / 32 * 444.8, abs=2)
    assert all((tmp / "photos" / f"video{job_id}_f{i:05d}.jpg").stat().st_size > 1000 for i in range(6))

    video_jobs.process_job(job_id)  # running again (e.g. after a restart) does not duplicate frames
    with Session(engine) as db:
        assert len(db.scalars(select(models.Observation).where(models.Observation.video_job_id == job_id)).all()) == 6

    gone = client.delete(f"/api/sentinel/videos/jobs/{job_id}").json()
    assert gone["observations_removed"] == 6
    assert list((tmp / "photos").glob(f"video{job_id}_*")) == [] and clip.exists()  # asset video untouched
    assert client.get(f"/api/sentinel/videos/jobs/{job_id}").status_code == 404


def test_video_job_errors(env, tmp_path, clip):
    client, _ = env
    ref = f"asset:test_pattern.mp4"
    base = {"video_ref": ref, "sentinel_label": "Test #01", "waypoints": [A, C], "recorded_at_ist": "2026-10-29T23:00"}
    assert client.post("/api/sentinel/videos/jobs", json={**base, "recorded_at_ist": "2099-01-01T00:00"}).json()["detail"]["code"] == "future_time"
    assert client.post("/api/sentinel/videos/jobs", json={**base, "recorded_at_ist": None}).json()["detail"]["code"] == "no_time"
    assert client.post("/api/sentinel/videos/jobs", json={**base, "waypoints": [A, [LAT, 95.0]]}).json()["detail"]["code"] == "too_far"
    assert client.post("/api/sentinel/videos/jobs", json={**base, "video_ref": "asset:../../secret.mp4"}).status_code == 404
    assert client.get("/api/sentinel/videos/assets/..%2F..%2Fapp%2Fmain.py").status_code == 404

    bad = client.post("/api/sentinel/videos/uploads", files={"file": ("ride.txt", b"hello", "text/plain")})
    assert bad.status_code == 415 and bad.json()["detail"]["code"] == "unsupported_format"
    broken = client.post("/api/sentinel/videos/uploads", files={"file": ("ride.mp4", b"not really a video", "video/mp4")})
    assert broken.status_code == 422 and broken.json()["detail"]["code"] == "unreadable"
    assert list((tmp_path / "uploads").glob("*")) == []  # rejected uploads are not kept

    good = client.post("/api/sentinel/videos/uploads", files={"file": ("My Night Ride.mp4", clip.read_bytes(), "video/mp4")})
    assert good.status_code == 200 and good.json()["name"] == "My Night Ride.mp4"
    job = client.post("/api/sentinel/videos/jobs", json={**base, "video_ref": good.json()["video_ref"]}).json()
    assert job["original_name"] == "My_Night_Ride.mp4" and job["source_kind"] == "upload"


def test_live_photo_rules(env):
    client, _ = env

    def send(lat, lon=92.0, acc=8.0, data=JPEG, device="device-test-1"):
        return client.post("/api/sentinel/photo", files={"image": ("p.jpg", data, "image/jpeg")}, data={
            "lat": lat, "lon": lon, "accuracy_m": acc, "sentinel_label": "Rapido #02", "device_id": device})

    ok = send(LAT + 0.0005)
    assert ok.status_code == 200 and ok.json()["street_name"] == "Sentinel Test Rd"
    assert send(LAT + 0.0006).json()["detail"]["code"] == "duplicate"  # ~11 m from the last photo
    assert send(LAT + 0.0015).status_code == 200  # ~111 m further on
    assert send(LAT + 0.001, acc=80).json()["detail"]["code"] == "gps_inaccurate"
    assert send(LAT + 0.001, lon=92.001).json()["detail"]["code"] == "off_street"  # ~98 m from the street
    assert send(LAT + 0.003, data=b"GIF89a....").json()["detail"]["code"] == "not_jpeg"
    with Session(engine) as db:
        o = db.get(models.Observation, ok.json()["observation_id"])
        assert o.position_source == "gps" and o.analysis_status == "pending" and o.photo_delete_at > o.captured_at
