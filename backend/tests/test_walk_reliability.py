"""Audit fixes #85-#88: finished walks stay finished, SOS / duress PIN after the end (decision B), version-checked
walk writes (clock vs. walker requests), and safe index creation on an existing database. Isolated test database."""

import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, make_engine, utcnow
from app.main import app
from app.services import walks as W
from app.services.geo import line_length_m

T = config.WALK_TIMERS
POLICE = {"X-Police-Token": "test-police-code"}
LAT, LON = 45.0, 105.0  # this file's own test lane (~550 m), far from any real map


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 490001)).first():
            pts = [[LAT, LON + 0.001 * i] for i in range(6)]
            for i in range(5):
                g = [pts[i], pts[i + 1]]
                db.add(models.Street(osm_way_id=490001 + i, name="Reliability Lane", road_type="residential", road_class="residential",
                                     start_node=490000 + i, end_node=490001 + i, length_m=line_length_m(g), geometry=g, city="guwahati"))
            db.commit()
    with TestClient(app) as c:
        yield c


def start(c):
    r = c.post("/api/walks", json={"walker_name": "Ravi", "contacts": [{"name": "Friend"}], "pin": "1111", "duress_pin": "9999",
                                   "start": {"lat": LAT, "lon": LON + 0.0001}, "end": {"lat": LAT, "lon": LON + 0.0049}})
    assert r.status_code == 200, r.text
    return r.json()["walk_id"], {"X-Walk-Token": r.json()["walker_token"]}


def finish(c, how):
    """A walk in one of the three terminal states."""
    wid, me = start(c)
    if how == "arrived":
        assert c.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.0049, "accuracy_m": 8}, headers=me).json()["status"] == "arrived"
    elif how == "ended":
        assert c.post(f"/api/walks/{wid}/end", json={"pin": "1111"}, headers=me).status_code == 200
    else:
        with SessionLocal() as db:
            db.get(models.Walk, wid).started_at = utcnow() - timedelta(hours=config.WALK_MAX_HOURS, minutes=1)
            db.commit()
        tick(0)
    return wid, me


def tick(seconds):
    with SessionLocal() as db:
        W.evaluate_all(db, utcnow() + timedelta(seconds=seconds))


def row(wid):
    with SessionLocal() as db:
        w = db.get(models.Walk, wid)
        alerts = [(a.level, a.trigger, a.status) for a in db.scalars(select(models.Alert).where(models.Alert.walk_id == wid)).all()]
        return w.status, w.escalation, [e["kind"] for e in w.events or []], alerts, w.version


def police_alerts(c, wid):
    return [a for a in c.get("/api/police/alerts", params={"city": "guwahati"}, headers=POLICE).json()["alerts"] if a["walk_id"] == wid]


# ---------------- #85: finished walks stay finished ----------------

@pytest.mark.parametrize("how", ["arrived", "ended", "expired"])
def test_no_pin_restarts_a_finished_walk(client, how):
    wid, me = finish(client, how)
    before = row(wid)
    answers = [client.post(f"/api/walks/{wid}/safe", json={"pin": p}, headers=me) for p in ("1111", "0000")]
    assert [a.status_code for a in answers] == [409, 409] and answers[0].json() == answers[1].json()
    assert answers[0].json()["detail"]["code"] == "walk_finished"
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "1111"}, headers=me).status_code == 409
    after = row(wid)
    assert after[0] == how and after[:4] == before[:4]  # status, escalation, timeline, alerts unchanged
    state = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert state["sharing"] is False and state["status"] == how
    view = client.get(f"/api/walks/{wid}/contact").json()
    assert view["status"] == how and view["last"] is None and view["route"] is None
    pos = client.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.002}, headers=me).json()
    assert pos["sharing"] is False and row(wid)[0] == how  # positions are still refused
    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 10)  # the clock never picks it up again
    assert row(wid)[:4] == after[:4]


@pytest.mark.parametrize("how", ["arrived", "ended", "expired"])
def test_duress_pin_after_the_end_alerts_police_silently(client, how):
    wid, me = finish(client, how)
    r = client.post(f"/api/walks/{wid}/safe", json={"pin": "9999"}, headers=me)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "walk_finished"  # same answer as the real PIN
    status, _, kinds, alerts, _ = row(wid)
    assert status == how and alerts == [("police", "duress_after_end", "new")] and "duress_after_end" in kinds
    [a] = police_alerts(client, wid)
    assert a["duress"] is True and a["live_position"] is None


def test_active_walk_pins_still_work(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me).json()["status"] == "active"
    assert row(wid)[3] == [("ask", "stopped", "resolved")]
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "0000"}, headers=me).status_code == 403
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "9999"}, headers=me).json()["status"] == "active"  # duress: looks normal
    assert police_alerts(client, wid)[0]["duress"] is True


# ---------------- #86: SOS after the end (decision B) ----------------

@pytest.mark.parametrize("how", ["arrived", "ended", "expired"])
def test_sos_after_the_end_alerts_police_and_walk_stays_finished(client, how):
    wid, me = finish(client, how)
    for _ in range(3):  # repeated presses: one alert
        assert client.post(f"/api/walks/{wid}/sos", headers=me).status_code == 200
    status, escalation, kinds, alerts, _ = row(wid)
    assert status == how and alerts == [("police", "sos_after_end", "new")]
    assert kinds.count("sos_after_end") == 3
    state = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert state["sharing"] is False and state["asking"] is False
    pos = client.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.002}, headers=me).json()
    assert pos["sharing"] is False  # GPS monitoring does not resume
    view = client.get(f"/api/walks/{wid}/contact").json()
    assert view["status"] == how and view["last"] is None and view["route"] is None
    assert any(e["kind"] == "sos_after_end" and "AFTER the walk" in e["text"] for e in view["events"])
    [a] = police_alerts(client, wid)
    assert a["trigger"] == "sos_after_end" and a["live_position"] is None
    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 10)
    assert row(wid)[0] == how and len(row(wid)[3]) == 1  # no clock escalation on a finished walk


def test_police_can_handle_an_sos_after_the_end(client):
    wid, me = finish(client, "ended")
    client.post(f"/api/walks/{wid}/sos", headers=me)
    [a] = police_alerts(client, wid)
    for st in ("acknowledged", "unit_sent", "resolved"):
        r = client.post(f"/api/police/alerts/{a['id']}/status", params={"city": "guwahati"}, json={"status": st}, headers=POLICE)
        assert r.status_code == 200
    assert row(wid)[0] == "ended"
    client.post(f"/api/walks/{wid}/sos", headers=me)  # a new press after resolution is a new emergency
    assert [x[2] for x in row(wid)[3]] == ["resolved", "new"]


def test_sos_hold_finishing_just_after_arrival(client):
    """The 2-s SOS hold was started on a running walk; arrival is committed before the SOS request is written."""
    wid, me = start(client)
    with SessionLocal() as sos_db:
        walk = sos_db.get(models.Walk, wid)  # the SOS request has read the walk while it was still active
        assert walk.status == "active"
        client.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.0049, "accuracy_m": 8}, headers=me)
        W.save(sos_db, walk, lambda: W.sos(sos_db, walk, utcnow()))
    status, escalation, kinds, alerts, _ = row(wid)
    assert status == "arrived" and escalation == 0
    assert alerts == [("police", "sos_after_end", "new")] and kinds.count("arrived") == 1 and "sos_after_end" in kinds


def test_sos_hold_finishing_just_after_end(client):
    wid, me = start(client)
    with SessionLocal() as sos_db:
        walk = sos_db.get(models.Walk, wid)
        _ = walk.status
        client.post(f"/api/walks/{wid}/end", json={"pin": "1111"}, headers=me)
        W.save(sos_db, walk, lambda: W.sos(sos_db, walk, utcnow()))
    status, _, kinds, alerts, _ = row(wid)
    assert status == "ended" and alerts == [("police", "sos_after_end", "new")] and kinds.count("ended") == 1


# ---------------- #87: version-checked walk writes ----------------

def test_stale_clock_round_cannot_overwrite_sos_repeatedly(client):
    for _ in range(10):
        wid, me = start(client)
        with SessionLocal() as clock_db:
            walk = clock_db.get(models.Walk, wid)
            _ = walk.status, walk.events  # the clock read the walk
            assert client.post(f"/api/walks/{wid}/sos", headers=me).status_code == 200  # SOS commits first
            W.save(clock_db, walk, lambda: W.tick(clock_db, walk, utcnow() + timedelta(seconds=T["stop_s"] + 1)))
        status, escalation, kinds, alerts, version = row(wid)
        assert status == "alert" and escalation == 3
        assert kinds.count("sos") == 1 and kinds.count("check") == 0  # SOS kept; the stale "stopped" check discarded
        assert [a for a in alerts if a[0] == "police"] == [("police", "sos", "new")]


def test_stale_write_is_refused_by_the_database(client):
    wid, me = start(client)
    with SessionLocal() as stale:
        walk = stale.get(models.Walk, wid)
        _ = walk.events
        client.post(f"/api/walks/{wid}/sos", headers=me)
        walk.events = []  # a blind overwrite from the old copy...
        with pytest.raises(Exception):
            stale.commit()  # ...is rejected (version check), never silently written
        stale.rollback()
    assert "sos" in row(wid)[2]


def test_two_simultaneous_sos_requests_make_one_police_alert(client):
    wid, me = start(client)
    with SessionLocal() as a_db, SessionLocal() as b_db:
        a, b = a_db.get(models.Walk, wid), b_db.get(models.Walk, wid)
        _ = a.status, b.status  # both requests read the walk before either wrote
        W.save(a_db, a, lambda: W.sos(a_db, a, utcnow()))
        W.save(b_db, b, lambda: W.sos(b_db, b, utcnow()))
    _, _, kinds, alerts, _ = row(wid)
    assert [x for x in alerts if x[0] == "police"] == [("police", "sos", "new")]
    assert kinds.count("sos") == 2  # "pressed SOS" + "pressed SOS again": both kept, nothing lost


def test_clock_and_sos_running_in_parallel_threads(client):
    for _ in range(5):
        wid, me = start(client)
        go = threading.Event()
        errors = []

        def clock():
            go.wait()
            try:
                for _ in range(5):
                    tick(T["stop_s"] + 1)
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)

        def press():
            go.wait()
            try:
                with SessionLocal() as db:
                    walk = db.get(models.Walk, wid)
                    W.save(db, walk, lambda: W.sos(db, walk, utcnow()))
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=clock), threading.Thread(target=press)]
        for t in threads:
            t.start()
        go.set()
        for t in threads:
            t.join(timeout=30)
        assert not errors, errors
        status, escalation, kinds, alerts, _ = row(wid)
        assert escalation == 3 and status == "alert" and kinds.count("sos") == 1
        assert [a for a in alerts if a[0] == "police"] == [("police", "sos", "new")]
        assert kinds.count("check") <= 1 and kinds.count("alert_contacts") <= 1


def test_active_escalation_unchanged_by_the_new_clock(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    tick(T["stop_s"] + T["ask_s"] + 2)
    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 5)
    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 10)  # extra rounds add nothing
    status, escalation, kinds, alerts, _ = row(wid)
    assert status == "alert" and escalation == 3
    assert [a[0] for a in alerts] == ["ask", "contacts", "police"] and kinds.count("alert_police") == 1


# ---------------- #88: upgrading an existing database ----------------

def test_upgrade_adds_columns_indexes_and_versions_without_touching_data(tmp_path):
    old = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    init_db(old)
    with old.begin() as conn:  # make it look like a database from before multi-city / indexes / versions
        for ix in ("ix_walks_city", "ix_walks_status", "ix_streets_city", "ix_places_city", "ix_reports_device_created",
                   "ix_reports_place_id", "ix_observations_device_captured"):
            conn.execute(text(f"DROP INDEX {ix}"))
        conn.execute(text("ALTER TABLE walks DROP COLUMN city"))
        conn.execute(text("ALTER TABLE walks DROP COLUMN version"))
        conn.execute(text("INSERT INTO walks (id, walker_name, route, dest_lat, dest_lon, pin_hash, status, started_at, events) "
                          "VALUES ('old-walk-1', 'Old Walker', '[]', 1.0, 2.0, 'x$y', 'ended', '2026-10-29 10:00:00', '[]')"))
        conn.execute(text("INSERT INTO streets (osm_way_id, name, road_type, road_class, start_node, end_node, length_m, geometry, in_demo_area) "
                          "VALUES (1, 'Old Road', 'residential', 'residential', 1, 2, 10.0, '[[1,2],[1,2.0001]]', 1)"))
        conn.execute(text("UPDATE streets SET city = NULL"))
    for _ in range(2):  # safe to run on every start
        init_db(old)
    insp = inspect(old)
    names = {ix["name"] for t in ("walks", "streets", "places", "reports", "observations") for ix in insp.get_indexes(t)}
    assert {"ix_walks_city", "ix_walks_status", "ix_streets_city", "ix_places_city", "ix_reports_device_created",
            "ix_reports_place_id", "ix_observations_device_captured"} <= names
    with old.connect() as conn:
        assert conn.execute(text("SELECT walker_name, city, version, status FROM walks")).one() == ("Old Walker", "guwahati", 1, "ended")
        assert conn.execute(text("SELECT name, city FROM streets")).one() == ("Old Road", "guwahati")
    with Session(old) as db:  # the upgraded old walk can be updated through the version check
        w = db.get(models.Walk, "old-walk-1")
        w.events = [{"at": "x", "kind": "note", "text": "t"}]
        db.commit()
        assert w.version == 2
    old.dispose()
