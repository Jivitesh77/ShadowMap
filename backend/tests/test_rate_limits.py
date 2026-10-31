"""Request limits per client (agreed: route 30 / min, help point 30 / min, walk start 5 / min, briefing 10 / min).
The general suite runs with very high limits (conftest); here the agreed values are set explicitly. A fake clock moves
time; one test restarts a real server to show that the in-memory counts reset on restart. Isolated test database."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine, init_db
from app.main import app
from app.rate_limit import limiter
from app.services.geo import line_length_m

BACKEND = Path(__file__).resolve().parents[1]
AGREED = {"route": 30, "help_point": 30, "walk_start": 5, "briefing": 10}
# Finalization: per-connection limits for reports (per hour), the map and where-am-I (per minute).
ADDED = {"report": 120, "map": 240, "where_am_i": 120}
DEFAULTS = {**AGREED, **ADDED}
LANES = {"guwahati": (57.0, 117.0, 880701), "delhi": (58.0, 118.0, 880801)}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture(scope="module", autouse=True)
def streets():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 880701)).first():
            for city, (lat, lon, base) in LANES.items():
                pts = [[lat, lon + 0.001 * i] for i in range(4)]
                for i in range(3):
                    g = [pts[i], pts[i + 1]]
                    db.add(models.Street(osm_way_id=base + i, name=f"Limit Lane {city}", road_type="residential", road_class="residential",
                                         start_node=base + i, end_node=base + i + 1, length_m=line_length_m(g), geometry=g, city=city))
            db.commit()


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(config, "RATE_LIMITS", dict(DEFAULTS))
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 0)
    monkeypatch.setattr(limiter, "clock", fake)
    limiter.reset()
    yield fake
    limiter.reset()


def client(ip="203.0.113.10"):
    return TestClient(app, client=(ip, 50000))


def route_body(city="guwahati"):
    lat, lon, _ = LANES[city]
    return {"start": {"lat": lat, "lon": lon + 0.0001}, "end": {"lat": lat, "lon": lon + 0.0029}, "city": city}


CALLS = {
    "route": lambda c, city="guwahati": c.post("/api/route", json=route_body(city)),
    "help_point": lambda c, city="guwahati": c.post("/api/help-point", json={"lat": LANES[city][0], "lon": LANES[city][1] + 0.001, "city": city}),
    "walk_start": lambda c, city="guwahati": c.post("/api/walks", json={**route_body(city), "walker_name": "Limit Test",
                                                                        "contacts": [{"name": "Friend"}], "pin": "1111"}),
    "briefing": lambda c, city="guwahati": c.post("/api/route/briefing", json={**route_body(city), "lang": "en"}),
}


def test_agreed_defaults_and_safe_parsing(monkeypatch):
    for name in ("ROUTE_PER_MIN", "HELP_POINT_PER_MIN", "WALK_START_PER_MIN", "BRIEFING_PER_MIN", "REPORT_PER_HOUR", "MAP_PER_MIN",
                 "WHERE_AM_I_PER_MIN"):
        monkeypatch.delenv(f"RATE_LIMIT_{name}", raising=False)
    assert config.rate_limits_from_env() == DEFAULTS
    monkeypatch.setenv("RATE_LIMIT_ROUTE_PER_MIN", "45")
    monkeypatch.setenv("RATE_LIMIT_HELP_POINT_PER_MIN", "lots")  # invalid -> agreed default
    monkeypatch.setenv("RATE_LIMIT_WALK_START_PER_MIN", "-3")  # negative -> agreed default
    monkeypatch.setenv("RATE_LIMIT_BRIEFING_PER_MIN", "0")  # 0 = switched off
    assert config.rate_limits_from_env() == {**DEFAULTS, "route": 45, "briefing": 0}


@pytest.mark.parametrize("category", list(AGREED))
def test_requests_up_to_the_limit_succeed_and_the_next_gets_429(clock, category):
    with client() as c:
        for i in range(AGREED[category]):
            r = CALLS[category](c)
            assert r.status_code == 200, (category, i, r.text)
        blocked = CALLS[category](c)
    assert blocked.status_code == 429
    detail = blocked.json()["detail"]
    assert detail["code"] == "rate_limited" and f"limit {AGREED[category]}" in detail["message"]
    retry = int(blocked.headers["Retry-After"])
    assert 1 <= retry <= 60 and detail["retry_after_s"] == retry


def test_retry_after_is_accurate_and_access_returns_after_the_window(clock):
    with client() as c:
        for _ in range(5):
            assert CALLS["walk_start"](c).status_code == 200
            clock.now += 10  # one walk start every 10 s
        r = CALLS["walk_start"](c)  # 50 s after the first one
        assert r.status_code == 429 and r.headers["Retry-After"] == "10"
        clock.now += 5
        assert CALLS["walk_start"](c).headers["Retry-After"] == "5"  # refused attempts do not extend the wait
        clock.now += 5
        assert CALLS["walk_start"](c).status_code == 200  # the oldest start is now a minute old


def test_each_endpoint_has_its_own_allowance(clock):
    with client() as c:
        for _ in range(5):
            CALLS["walk_start"](c)
        assert CALLS["walk_start"](c).status_code == 429
        assert CALLS["route"](c).status_code == 200 and CALLS["help_point"](c).status_code == 200
        assert CALLS["briefing"](c).status_code == 200


def test_different_clients_are_limited_independently(clock):
    with client("203.0.113.20") as a, client("203.0.113.21") as b:
        for _ in range(5):
            assert CALLS["walk_start"](a).status_code == 200
        assert CALLS["walk_start"](a).status_code == 429
        assert CALLS["walk_start"](b).status_code == 200  # another client is not affected


def test_faked_forwarding_headers_cannot_bypass_limits_without_a_proxy(clock):
    with client() as c:  # TRUSTED_PROXY_HOPS = 0: X-Forwarded-For is ignored completely
        for i in range(5):
            assert c.post("/api/walks", headers={"X-Forwarded-For": f"198.51.100.{i}"}, json={
                **route_body(), "walker_name": "x", "contacts": [{"name": "a"}], "pin": "1111"}).status_code == 200
        r = c.post("/api/walks", headers={"X-Forwarded-For": "198.51.100.99"},
                   json={**route_body(), "walker_name": "x", "contacts": [{"name": "a"}], "pin": "1111"})
    assert r.status_code == 429


def test_behind_render_only_the_proxy_appended_address_counts(clock, monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 1)
    body = {**route_body(), "walker_name": "x", "contacts": [{"name": "a"}], "pin": "1111"}
    with client("10.10.0.5") as proxy:  # every request arrives from Render's proxy address
        for i in range(5):  # the client writes a different fake address each time; the proxy appends the real one
            assert proxy.post("/api/walks", json=body, headers={"X-Forwarded-For": f"6.6.6.{i}, 203.0.113.50"}).status_code == 200
        assert proxy.post("/api/walks", json=body, headers={"X-Forwarded-For": "7.7.7.7, 203.0.113.50"}).status_code == 429
        # another real client behind the same proxy has its own allowance
        assert proxy.post("/api/walks", json=body, headers={"X-Forwarded-For": "203.0.113.51"}).status_code == 200
        # a request without the proxy's header falls back to the connection address, never to a guess
        assert proxy.post("/api/walks", json=body).status_code == 200


def test_switching_city_does_not_give_a_fresh_allowance(clock):
    with client() as c:
        for i in range(5):
            assert CALLS["walk_start"](c, "delhi" if i % 2 else "guwahati").status_code == 200
        assert CALLS["walk_start"](c, "delhi").status_code == 429
        assert CALLS["walk_start"](c, "guwahati").status_code == 429


def test_failed_requests_count_and_429_is_consistent(clock):
    with client() as c:
        for _ in range(29):
            assert c.post("/api/route", json={"start": {"lat": 95, "lon": 0}}).status_code == 422  # invalid: still counts
        assert c.post("/api/route", json={**route_body(), "city": "atlantis"}).status_code == 404  # 30th: unknown city
        r = c.post("/api/route", json=route_body())
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"


def test_safety_actions_and_other_endpoints_are_never_limited(clock):
    with client() as c:
        r = CALLS["walk_start"](c).json()
        wid, me = r["walk_id"], {"X-Walk-Token": r["walker_token"]}
        for _ in range(5):
            CALLS["walk_start"](c)  # walk starts now exhausted for this client
        lat, lon, _ = LANES["guwahati"]
        for _ in range(40):
            assert c.post(f"/api/walks/{wid}/position", json={"lat": lat, "lon": lon + 0.001}, headers=me).status_code == 200
        for _ in range(10):
            assert c.post(f"/api/walks/{wid}/sos", headers=me).status_code == 200
        assert c.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me).status_code == 200
        for _ in range(40):
            assert c.get("/api/map", params={"city": "guwahati"}).status_code == 200
        assert c.get(f"/api/walks/{wid}/contact").status_code == 200
        # access codes still work as before
        assert c.get("/api/police/alerts").status_code == 401
        assert c.get("/api/police/alerts", headers={"X-Police-Token": "test-police-code"}).status_code == 200


def test_browser_can_read_the_429_and_retry_after_across_origins(clock, monkeypatch):
    origin = config.CORS_ORIGINS[0]
    with client() as c:
        for _ in range(5):
            CALLS["walk_start"](c)
        r = c.post("/api/walks", headers={"Origin": origin},
                   json={**route_body(), "walker_name": "x", "contacts": [{"name": "a"}], "pin": "1111"})
    assert r.status_code == 429
    assert r.headers["access-control-allow-origin"] == origin
    assert "retry-after" in r.headers["access-control-expose-headers"].lower()


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server(tmp_path, port):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'rl.db'}", "DATA_DIR": str(tmp_path / "data"), "START_WORKERS": "0",
           "RATE_LIMIT_ROUTE_PER_MIN": "2", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.terminate()
    raise AssertionError("test server did not start")


def test_limits_are_in_memory_and_reset_when_the_server_restarts(tmp_path):
    port = _free_port()
    url = f"http://127.0.0.1:{port}/api/route"
    proc = _server(tmp_path, port)
    try:
        codes = [httpx.post(url, json={}, timeout=5).status_code for _ in range(3)]
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    assert codes == [422, 422, 429]  # limit 2: the third request in the minute is refused
    proc = _server(tmp_path, port)  # restart (same database)
    try:
        after = httpx.post(url, json={}, timeout=5).status_code
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    assert after == 422  # counts are kept in memory only: a restart starts from zero (documented)
