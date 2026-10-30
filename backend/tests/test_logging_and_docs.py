"""Logging never contains trip-link secrets (walk ids), names, phones or positions; API docs pages follow API_DOCS.
Server-level checks start a separate backend process on a throwaway database, so the real uvicorn output is examined."""

import logging
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
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.logging_setup import RedactWalkIds, redact_walk_paths, setup_logging, walk_ref
from app.main import app
from app.services import walks as W
from app.services.geo import line_length_m

BACKEND = Path(__file__).resolve().parents[1]
LAT, LON = 53.0, 113.0  # this file's own test lane, far from any real map


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 880301)).first():
            pts = [[LAT, LON + 0.001 * i] for i in range(6)]
            for i in range(5):
                g = [pts[i], pts[i + 1]]
                db.add(models.Street(osm_way_id=880301 + i, name="Log Lane", road_type="residential", road_class="residential",
                                     start_node=880300 + i, end_node=880301 + i, length_m=line_length_m(g), geometry=g, city="guwahati"))
            db.commit()
    with TestClient(app) as c:
        yield c


def start_walk(c, name="Meera Log", phone="+91 98765 43210"):
    r = c.post("/api/walks", json={"walker_name": name, "walker_phone": phone, "contacts": [{"name": "Friend", "phone": "91234 56789"}],
                                   "pin": "1111", "start": {"lat": LAT, "lon": LON + 0.0001}, "end": {"lat": LAT, "lon": LON + 0.0049}})
    assert r.status_code == 200, r.text
    return r.json()["walk_id"], {"X-Walk-Token": r.json()["walker_token"]}


# ---------------- API docs setting ----------------

@pytest.mark.parametrize("value, expected", [
    (None, True), ("", True), ("  ", True), ("true", True), ("1", True), ("YES", True), ("on", True),
    ("false", False), ("0", False), ("no", False), ("off", False), ("ture", False), ("disabled", False),
])
def test_api_docs_setting_parsing(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("API_DOCS", raising=False)
    else:
        monkeypatch.setenv("API_DOCS", value)
    assert config._api_docs() is expected  # unset/empty = on locally; a typo hides the pages, never shows them


def test_api_docs_available_by_default(client):
    assert config.API_DOCS is True
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "ShadowMap API"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_server(tmp_path, extra_env: dict, requests):
    """Start the real backend (uvicorn) on a throwaway database, make `requests(base_url)`, return all output."""
    port = _free_port()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'server.db'}", "DATA_DIR": str(tmp_path),
           "START_WORKERS": "0", "PYTHONDONTWRITEBYTECODE": "1", **extra_env}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise AssertionError("test server did not start")
        result = requests(base)
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=20)
    return result, out


def test_api_docs_off_in_production_and_api_still_works(tmp_path):
    def calls(base):
        return {p: httpx.get(base + p, timeout=5).status_code for p in ("/docs", "/redoc", "/openapi.json", "/api/health", "/api/cities")}
    codes, _ = run_server(tmp_path, {"API_DOCS": "false"}, calls)
    assert codes == {"/docs": 404, "/redoc": 404, "/openapi.json": 404, "/api/health": 200, "/api/cities": 200}


# ---------------- No walk ids (or personal data) in logs ----------------

def test_walk_ref_is_short_stable_and_not_the_id():
    wid = "AbCdEfGh12345678"
    ref = walk_ref(wid)
    assert ref == walk_ref(wid) and ref != walk_ref("AbCdEfGh12345679")  # follow one walk through the log
    assert wid not in ref and len(ref) == len("walk-") + 10
    assert walk_ref(None) == "walk-unknown"


def test_request_paths_are_redacted_but_routes_stay_readable():
    wid = "Zx9_Yw8-Vu7Ts6Rq"
    assert redact_walk_paths(f"/api/walks/{wid}/contact") == f"/api/walks/{walk_ref(wid)}/contact"
    assert redact_walk_paths(f"/trip/{wid}") == f"/trip/{walk_ref(wid)}"
    for kept in ("/api/walks/config", "/api/walks", "/api/where-am-i", "/api/route"):
        assert redact_walk_paths(kept) == kept
    # uvicorn's access log passes the path as an argument: the filter rewrites it
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:5000", "GET", f"/api/walks/{wid}/state", "1.1", 200), None)
    RedactWalkIds().filter(rec)
    assert wid not in rec.getMessage() and walk_ref(wid) in rec.getMessage() and "/state" in rec.getMessage()


def test_real_server_access_log_never_contains_walk_ids(tmp_path):
    wid = "QwErTy123456_-Ab"

    def calls(base):
        httpx.get(f"{base}/api/walks/{wid}/contact", timeout=5)  # what a trusted contact's page polls
        httpx.post(f"{base}/api/walks/{wid}/sos", timeout=5)
        httpx.get(f"{base}/api/walks/config", timeout=5)
    _, out = run_server(tmp_path, {}, calls)
    assert f"/api/walks/{walk_ref(wid)}/contact" in out and "/api/walks/config" in out  # requests are still logged
    assert wid not in out


def test_walk_conflict_logs_use_the_reference_only(client, caplog):
    wid, me = start_walk(client)
    caplog.set_level(logging.INFO, logger="shadowmap")
    with SessionLocal() as stale:  # the clock holds an old copy while an SOS is committed
        walk = stale.get(models.Walk, wid)
        _ = walk.events
        client.post(f"/api/walks/{wid}/sos", headers=me)
        W.save(stale, walk, lambda: W.tick(stale, walk, utcnow() + timedelta(seconds=config.WALK_TIMERS["stop_s"] + 1)))
    msgs = [r.getMessage() for r in caplog.records if r.name.startswith("shadowmap")]
    assert any(walk_ref(wid) in m and "changed meanwhile" in m for m in msgs), msgs  # still useful for debugging
    text = "\n".join(msgs)
    assert wid not in text and "Meera" not in text and "98765" not in text and str(LAT) not in text


def test_giving_up_logs_a_warning_with_the_reference_only(client, caplog):
    wid, me = start_walk(client)
    caplog.set_level(logging.INFO, logger="shadowmap")
    with SessionLocal() as db:
        walk = db.get(models.Walk, wid)

        def always_stale():  # this copy is read, then someone else commits a newer version, every time
            _ = walk.version, walk.events
            with SessionLocal() as other:
                w = other.get(models.Walk, wid)
                w.events = [*(w.events or []), {"at": "x", "kind": "note", "text": "t"}]
                other.commit()
            walk.battery_pct = 50

        with pytest.raises(W.WalkConflict) as err:
            W.save(db, walk, always_stale, attempts=2)
    assert str(err.value) == walk_ref(wid)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.name == "shadowmap.walks"]
    assert warnings and walk_ref(wid) in warnings[-1].getMessage() and wid not in warnings[-1].getMessage()


def test_database_errors_hide_stored_values(client):
    wid, _ = start_walk(client, name="Secret Name", phone="+91 90000 12345")
    with SessionLocal() as db:
        db.add(models.Walk(id=wid, walker_name="Secret Name", walker_phone="+91 90000 12345", route=[], dest_lat=1.0, dest_lon=2.0,
                           pin_hash="x$y", status="active"))
        with pytest.raises(IntegrityError) as err:
            db.commit()
    text = str(err.value)
    assert "UNIQUE constraint failed" in text  # the error itself stays useful
    assert wid not in text and "Secret Name" not in text and "90000" not in text and "hidden" in text


# ---------------- The logging setup itself ----------------

def test_warnings_and_errors_stay_visible_and_setup_is_idempotent(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "ERROR")  # even a strict level keeps warnings
    setup_logging()
    setup_logging()
    ours = logging.getLogger("shadowmap")
    handlers = [h for h in ours.handlers if getattr(h, "shadowmap_handler", False)]
    assert len(handlers) == 1 and ours.getEffectiveLevel() <= logging.WARNING
    assert any(isinstance(f, RedactWalkIds) for f in logging.getLogger("uvicorn.access").filters)
    assert sum(isinstance(f, RedactWalkIds) for f in logging.getLogger("uvicorn.access").filters) == 1
    monkeypatch.setenv("LOG_LEVEL", "nonsense")
    setup_logging()
    assert ours.getEffectiveLevel() == logging.INFO  # an unknown value falls back to INFO
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    setup_logging()


def test_existing_operational_messages_unchanged(caplog):
    """Video, photo and route-counter messages carry job / photo numbers and counts only — no change needed."""
    from app.routers.route import log as route_log
    from app.services.video_jobs import log as video_log
    caplog.set_level(logging.INFO, logger="shadowmap")
    video_log.info("removed %d abandoned video uploads", 2)
    route_log.warning("route-use counter not updated (%s, %d streets): database busy", "planned", 5)
    assert [r.getMessage() for r in caplog.records][-2:] == ["removed 2 abandoned video uploads",
                                                            "route-use counter not updated (planned, 5 streets): database busy"]
