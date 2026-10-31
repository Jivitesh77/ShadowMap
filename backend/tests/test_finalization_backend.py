"""Finalization fixes: report abuse limit per connection, map / where-am-I limits, the light "scores" map view, route
counting for automatic re-plans, missing FFmpeg handled clearly, honest arrival wording, health details.
Isolated test database; hand-made test lanes far from both real cities; fake clock for limits."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db
from app.main import app
from app.rate_limit import limiter
from app.services import video
from app.services.geo import line_length_m

LAT, LON = 61.0, 121.0
AUTH = {"X-Sentinel-Token": os.environ["SENTINEL_TOKEN"]}


class FakeClock:
    now = 5000.0

    def __call__(self):
        return self.now


@pytest.fixture(scope="module", autouse=True)
def lane():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 881101)).first():
            pts = [[LAT, LON + 0.001 * i] for i in range(5)]
            for i in range(4):
                g = [pts[i], pts[i + 1]]
                db.add(models.Street(osm_way_id=881101 + i, name="Final Lane", road_type="residential", road_class="residential",
                                     start_node=881100 + i, end_node=881101 + i, length_m=line_length_m(g), geometry=g, city="guwahati"))
            db.commit()


@pytest.fixture
def limits(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(config, "RATE_LIMITS", config.rate_limits_from_env() | {"report": 30, "map": 60, "where_am_i": 30})
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 0)
    monkeypatch.setattr(limiter, "clock", clock)
    limiter.reset()
    yield clock
    limiter.reset()


def report(c, device, kind="dark"):
    return c.post("/api/reports", json={"kind": kind, "lat": LAT, "lon": LON + 0.0015, "device_id": device, "city": "guwahati"})


# ---------------- Report abuse ----------------

def test_inventing_device_ids_no_longer_bypasses_the_report_limit(limits):
    with TestClient(app, client=("198.51.100.7", 1)) as c:
        codes = [report(c, f"fake-device-{i:03d}").status_code for i in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429  # 30 per hour per connection
    with TestClient(app, client=("198.51.100.7", 1)) as c:
        r = report(c, "yet-another-device")
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 60 and "hour" in r.json()["detail"]["message"]
    limits.now += 3601  # an hour later the connection may report again
    with TestClient(app, client=("198.51.100.7", 1)) as c:
        assert report(c, "device-after-an-hour").status_code == 200


def test_per_device_rule_still_applies_and_other_connections_are_independent(limits):
    with TestClient(app, client=("198.51.100.8", 1)) as c:
        codes = [report(c, "one-real-device", kind=k).status_code for k in ("dark", "deserted", "felt_unsafe", "well_lit", "broken_light", "dark")]
    assert codes[:5] == [200] * 5 and codes[5] == 429  # existing 5 per hour per device
    with TestClient(app, client=("198.51.100.9", 1)) as other:
        assert report(other, "neighbour-device").status_code == 200


def test_faked_forwarding_header_cannot_reset_the_report_limit(limits):
    with TestClient(app, client=("198.51.100.10", 1)) as c:
        for i in range(30):
            c.post("/api/reports", headers={"X-Forwarded-For": f"10.0.0.{i}"},
                   json={"kind": "dark", "lat": LAT, "lon": LON + 0.0015, "device_id": f"d{i:04d}", "city": "guwahati"})
        r = c.post("/api/reports", headers={"X-Forwarded-For": "10.9.9.9"},
                   json={"kind": "dark", "lat": LAT, "lon": LON + 0.0015, "device_id": "d9999", "city": "guwahati"})
    assert r.status_code == 429


def test_map_and_where_am_i_are_limited_per_connection(limits):
    with TestClient(app, client=("198.51.100.11", 1)) as c:
        maps = [c.get("/api/map", params={"city": "guwahati", "view": "scores"}).status_code for _ in range(61)]
        wheres = [c.post("/api/where-am-i", json={"lat": LAT, "lon": LON, "city": "guwahati"}).status_code for _ in range(31)]
        assert c.post(f"/api/walks/does-not-exist-12/position", json={"lat": LAT, "lon": LON}).status_code != 429  # safety actions never limited
    assert maps[:60] == [200] * 60 and maps[60] == 429
    assert wheres[:30] == [200] * 30 and wheres[30] == 429


# ---------------- Light map refresh ----------------

def test_scores_view_has_no_shapes_and_matches_the_full_map():
    with TestClient(app) as c:
        full = c.get("/api/map", params={"city": "guwahati", "at": "2026-10-30T23:30"}).json()
        light = c.get("/api/map", params={"city": "guwahati", "at": "2026-10-30T23:30", "view": "scores"}).json()
    assert full["view"] == "full" and light["view"] == "scores" and light["city"] == "guwahati"
    assert light["generated_utc"].endswith("Z") and full["generated_utc"].endswith("Z")  # data age can be shown
    assert all("geometry" not in s and "name" not in s for s in light["streets"])
    assert {s["id"]: (s["score"], s["colour"]) for s in light["streets"]} == {s["id"]: (s["score"], s["colour"]) for s in full["streets"]}
    assert {p["id"]: p["status"] for p in light["places"]} == {p["id"]: p["status"] for p in full["places"]}
    assert all(set(p) <= {"id", "status", "status_basis", "community_report", "confidence", "confidence_reason"} for p in light["places"])
    assert c.get("/api/map", params={"view": "everything"}).status_code == 422


# ---------------- Route counting ----------------

def test_automatic_replans_are_not_counted():
    body = {"start": {"lat": LAT, "lon": LON + 0.0001}, "end": {"lat": LAT, "lon": LON + 0.0039}}

    def total():
        with Session(engine) as db:
            return sum(u.planned or 0 for u in db.scalars(select(models.RouteUse)).all())
    with TestClient(app) as c:
        before = total()
        assert c.post("/api/route", json=body).status_code == 200  # the walker asks: counted
        after_first = total()
        for _ in range(3):
            assert c.post("/api/route", json={**body, "count": False}).status_code == 200  # refreshes: same route, not counted
    assert after_first > before and total() == after_first


# ---------------- Missing FFmpeg ----------------

def test_missing_video_tools_answer_503_and_keep_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VIDEO_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "FFMPEG_BIN", "ffmpeg-not-installed-here")
    monkeypatch.setattr(config, "FFPROBE_BIN", "ffprobe-not-installed-here")
    assert video.missing_video_tools() == ["ffmpeg", "ffprobe"]
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\0" * 2048)
    with TestClient(app) as c:
        with open(clip, "rb") as f:
            r = c.post("/api/sentinel/videos/uploads", files={"file": ("clip.mp4", f, "video/mp4")}, headers=AUTH)
        assert r.status_code == 503 and r.json()["detail"]["code"] == "video_tools_missing"
        assert "Live photos, maps, routes and walks still work" in r.json()["detail"]["message"]
        assert not (tmp_path / "uploads").exists() or list((tmp_path / "uploads").iterdir()) == []
        status = c.get("/api/sentinel/status").json()
        assert status["video_available"] is False and "FFmpeg" in status["video_note"]
        health = c.get("/api/health").json()
        assert health["video_tools"] == "missing" and health["status"] == "ok"  # the rest of the app is fine
        assert c.get("/api/map", params={"city": "guwahati"}).status_code == 200
    with pytest.raises(video.VideoError) as err:  # the processing step reports it instead of crashing
        video.probe(clip)
    assert err.value.code == "video_tools_missing"


def test_video_tools_present_in_this_environment():
    assert video.missing_video_tools() == []  # the laptop has FFmpeg; tests above simulate a server without it


# ---------------- Health details ----------------

def test_health_reports_checks_without_secrets():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
    assert h["status"] == "ok" and h["database"] == "ok" and h["face_blurring"] in ("ok", "unavailable")
    assert h["workers"].startswith("not started")  # tests run without the background threads
    text = str(h)
    assert os.environ["SENTINEL_TOKEN"] not in text and os.environ["POLICE_TOKEN"] not in text


def test_security_headers_on_api_responses_but_docs_still_load():
    with TestClient(app) as c:
        r = c.get("/api/health")
        docs = c.get("/docs")
        cors = c.get("/api/cities", headers={"Origin": config.CORS_ORIGINS[0]})
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers  # plain http locally
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers  # API pages keep working locally
    assert cors.headers["access-control-allow-origin"] == config.CORS_ORIGINS[0]  # CORS unaffected
    with TestClient(app, base_url="https://testserver") as c:
        assert "max-age" in c.get("/api/health").headers["strict-transport-security"]


def test_default_limits_do_not_block_a_class_on_one_hotspot(monkeypatch):
    """Final-review regression: one hotspot = one client. With the default limits, 40 phones opening the map (full +
    one score refresh each) and 40 walking phones (3 where-am-I a minute) within one minute are all served."""
    for name in ("REPORT_PER_HOUR", "MAP_PER_MIN", "WHERE_AM_I_PER_MIN"):
        monkeypatch.delenv(f"RATE_LIMIT_{name}", raising=False)
    defaults = config.rate_limits_from_env()
    assert (defaults["map"], defaults["where_am_i"], defaults["report"]) == (240, 120, 120)
    monkeypatch.setattr(config, "RATE_LIMITS", defaults)
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 0)
    monkeypatch.setattr(limiter, "clock", FakeClock())
    limiter.reset()
    try:
        with TestClient(app, client=("203.0.113.200", 1)) as hotspot:
            maps = [hotspot.get("/api/map", params={"city": "guwahati", "view": v}).status_code for _ in range(40) for v in ("full", "scores")]
            walks = [hotspot.post("/api/where-am-i", json={"lat": LAT, "lon": LON, "city": "guwahati"}).status_code for _ in range(120)]
        assert set(maps) == {200} and set(walks) == {200}
    finally:
        limiter.reset()
