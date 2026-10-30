"""Sentinel video jobs belong to one city: listing, viewing and deleting only ever see the selected city's jobs.
Generated test clip only (never real footage); hand-made test streets far from both real cities; isolated test database."""

import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db
from app.main import app
from app.services import video_jobs
from app.services.geo import line_length_m

# One straight ~440 m test lane per city (two pieces each), at coordinates no real map uses.
LANES = {"guwahati": (48.0, 108.0), "delhi": (49.0, 109.0)}


def lane(city):
    lat, lon = LANES[city]
    return [[lat, lon], [lat + 0.002, lon], [lat + 0.004, lon]]


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """A generated 12 s test pattern clip (not footage)."""
    p = tmp_path_factory.mktemp("videos") / "city_test_pattern.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10", "-t", "12",
                    "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


@pytest.fixture
def client(tmp_path, monkeypatch, clip):
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "VIDEO_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "ASSET_VIDEO_DIR", clip.parent)
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 860001)).first():
            for k, city in enumerate(LANES):
                pts = lane(city)
                for i in range(2):
                    g = [pts[i], pts[i + 1]]
                    db.add(models.Street(osm_way_id=860001 + 10 * k + i, name=f"Video Lane {city}", road_type="residential",
                                         road_class="residential", start_node=860000 + 10 * k + i, end_node=860001 + 10 * k + i,
                                         length_m=line_length_m(g), geometry=g, city=city))
            db.commit()
    with TestClient(app, headers={"X-Sentinel-Token": os.environ["SENTINEL_TOKEN"]}) as c:
        yield c


def make_job(c, clip, city, process=True):
    """A job created exactly as the Sentinel page does it (city sent with the job), then processed like the worker."""
    ref = c.get(f"/api/sentinel/videos/assets/{clip.name}").json()["video_ref"]
    body = {"video_ref": ref, "sentinel_label": f"Rider {city}", "waypoints": [lane(city)[0], lane(city)[2]],
            "recorded_at_ist": "2026-10-29T23:00:00", "frame_interval_s": 5}
    if city != "guwahati":
        body["city"] = city
    r = c.post("/api/sentinel/videos/jobs", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["city"] == city
    if process:
        video_jobs.process_job(r.json()["id"])
    return r.json()["id"]


def listed(c, city=None):
    r = c.get("/api/sentinel/videos/jobs", params={"city": city} if city else None)
    assert r.status_code == 200
    return r.json()


def observations(job_id):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(models.Observation).where(models.Observation.video_job_id == job_id))


def test_each_city_lists_only_its_own_jobs(client, clip):
    d, g = make_job(client, clip, "delhi"), make_job(client, clip, "guwahati")
    delhi, guwahati = listed(client, "delhi"), listed(client, "guwahati")
    assert delhi["city"] == "delhi" and guwahati["city"] == "guwahati"
    assert d in {j["id"] for j in delhi["jobs"]} and g not in {j["id"] for j in delhi["jobs"]}
    assert g in {j["id"] for j in guwahati["jobs"]} and d not in {j["id"] for j in guwahati["jobs"]}
    assert all(j["city"] == "delhi" for j in delhi["jobs"]) and all(j["city"] == "guwahati" for j in guwahati["jobs"])
    default = listed(client)  # no city = Guwahati, as before multi-city
    assert default["city"] == "guwahati" and {j["id"] for j in default["jobs"]} == {j["id"] for j in guwahati["jobs"]}


def test_delhi_job_frames_land_on_delhi_streets(client, clip):
    d = make_job(client, clip, "delhi")
    job = client.get(f"/api/sentinel/videos/jobs/{d}", params={"city": "delhi"}).json()
    assert job["status"] == "done" and job["city"] == "delhi"
    assert {s["name"] for s in job["streets_covered"]} == {"Video Lane delhi"}


def test_viewing_another_citys_job_is_not_found(client, clip):
    d, g = make_job(client, clip, "delhi"), make_job(client, clip, "guwahati")
    for job_id, wrong in ((d, "guwahati"), (g, "delhi")):
        r = client.get(f"/api/sentinel/videos/jobs/{job_id}", params={"city": wrong})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert client.get(f"/api/sentinel/videos/jobs/{d}").status_code == 404  # no city = Guwahati
    assert client.get(f"/api/sentinel/videos/jobs/{d}", params={"city": "delhi"}).status_code == 200
    assert client.get(f"/api/sentinel/videos/jobs/{g}").status_code == 200
    # a wrong-city answer looks exactly like a job that does not exist
    missing = client.get("/api/sentinel/videos/jobs/999999", params={"city": "guwahati"})
    assert missing.status_code == 404 and missing.json() == client.get(f"/api/sentinel/videos/jobs/{d}", params={"city": "guwahati"}).json()


def test_deleting_with_the_wrong_city_changes_nothing(client, clip):
    d, g = make_job(client, clip, "delhi"), make_job(client, clip, "guwahati")
    frames_d, frames_g = observations(d), observations(g)
    assert frames_d > 0 and frames_g > 0
    assert client.delete(f"/api/sentinel/videos/jobs/{d}", params={"city": "guwahati"}).status_code == 404
    assert client.delete(f"/api/sentinel/videos/jobs/{d}").status_code == 404  # no city = Guwahati
    assert client.delete(f"/api/sentinel/videos/jobs/{g}", params={"city": "delhi"}).status_code == 404
    assert observations(d) == frames_d and observations(g) == frames_g  # nothing removed
    assert client.get(f"/api/sentinel/videos/jobs/{d}", params={"city": "delhi"}).json()["status"] == "done"

    gone = client.delete(f"/api/sentinel/videos/jobs/{d}", params={"city": "delhi"})  # the right city works
    assert gone.status_code == 200 and gone.json()["observations_removed"] == frames_d
    assert client.get(f"/api/sentinel/videos/jobs/{d}", params={"city": "delhi"}).status_code == 404
    assert client.delete(f"/api/sentinel/videos/jobs/{g}").json()["observations_removed"] == frames_g  # default city


def test_unknown_city_and_missing_access_code(client, clip):
    g = make_job(client, clip, "guwahati", process=False)
    for method, path in (("get", "/api/sentinel/videos/jobs"), ("get", f"/api/sentinel/videos/jobs/{g}"),
                         ("delete", f"/api/sentinel/videos/jobs/{g}")):
        r = getattr(client, method)(path, params={"city": "atlantis"})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "unknown_city"
    with TestClient(app) as anonymous:  # the access code is still checked first
        for method, path in (("get", "/api/sentinel/videos/jobs"), ("get", f"/api/sentinel/videos/jobs/{g}"),
                             ("delete", f"/api/sentinel/videos/jobs/{g}")):
            assert getattr(anonymous, method)(path, params={"city": "guwahati"}).status_code == 401
    assert client.get(f"/api/sentinel/videos/jobs/{g}").json()["status"] == "queued"  # untouched
    video_jobs.process_job(g)
