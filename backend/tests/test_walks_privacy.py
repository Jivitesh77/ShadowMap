"""Walk With Me: access control, link revocation/expiry, GPS robustness, duplicate alerts, PIN lock-out, retention.
Isolated test database (conftest). No real numbers are ever called."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.main import app
from app.services import retention
from app.services.geo import line_length_m
from app.services.walks import evaluate_all

LAT, LON = 35.0, 98.0  # this file's own street (~285 m east-west)
PTS = [[LAT, LON], [LAT, LON + 0.001], [LAT, LON + 0.002], [LAT, LON + 0.003]]
START, END = {"lat": LAT, "lon": LON + 0.0001}, {"lat": LAT, "lon": LON + 0.0029}
T = config.WALK_TIMERS
POLICE = {"X-Police-Token": "test-police-code"}


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 450001)).first():
            for i in range(3):
                g = [PTS[i], PTS[i + 1]]
                db.add(models.Street(osm_way_id=450001 + i, name="Privacy Lane", road_type="residential", road_class="residential",
                                     start_node=450000 + i, end_node=450001 + i, length_m=line_length_m(g), geometry=g))
            db.commit()
    with TestClient(app) as c:
        yield c


def start(client, name="Asha", phone="+91 91111 11111", contact_phone="92222 22222"):
    r = client.post("/api/walks", json={"walker_name": name, "walker_phone": phone, "contacts": [{"name": "Sister", "phone": contact_phone}],
                                        "pin": "2468", "duress_pin": "1357", "start": START, "end": END})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["walk_id"], {"X-Walk-Token": d["walker_token"]}


def tick(seconds):
    with SessionLocal() as db:
        evaluate_all(db, utcnow() + timedelta(seconds=seconds))


def police_alerts_for(client, wid):
    return [a for a in client.get("/api/police/alerts", headers=POLICE).json()["alerts"] if a["walk_id"] == wid]


def test_links_are_random_and_contain_no_database_ids(client):
    ids = {start(client)[0] for _ in range(5)}
    assert len(ids) == 5 and all(len(i) >= 16 and not i.isdigit() for i in ids)


def test_public_trip_link_shows_no_phone_numbers(client):
    wid, me = start(client)
    text = client.get(f"/api/walks/{wid}/contact").text
    assert "91111" not in text and "92222" not in text and "phone" not in text
    assert "Sister" not in text  # other contacts' names are not shown either


def test_two_trips_cannot_touch_each_other(client):
    a, a_tok = start(client, name="Walker A")
    b, b_tok = start(client, name="Walker B")
    assert client.post(f"/api/walks/{b}/safe", json={"pin": "2468"}, headers=a_tok).status_code == 403
    assert client.post(f"/api/walks/{b}/sos", headers=a_tok).status_code == 403
    assert client.post(f"/api/walks/{b}/end", json={"pin": "2468"}, headers=a_tok).status_code == 403
    assert client.post(f"/api/walks/{b}/position", json={"lat": LAT, "lon": LON}, headers=a_tok).status_code == 403
    assert client.get(f"/api/walks/{b}/state", headers=a_tok).status_code == 403
    assert client.get(f"/api/walks/{a}/contact").json()["walker_name"] == "Walker A"
    assert client.get("/api/walks/not-a-real-trip-id/contact").status_code == 404
    tick(T["stop_s"] + 1)
    assert client.get(f"/api/walks/{a}/state", headers=a_tok).json()["asking"]
    assert client.get(f"/api/walks/{b}/state", headers=b_tok).json()["asking"]  # both clocks run independently


def test_end_stops_sharing_at_once_and_link_shows_final_status_only(client):
    wid, me = start(client)
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "2468"}, headers=me).status_code == 200
    c = client.get(f"/api/walks/{wid}/contact").json()
    assert c["status"] == "ended" and c["last"] is None and c["route"] is None and c["dest"] is None
    assert len(c["events"]) == 1 and "ended the walk" in c["events"][0]["text"]
    r = client.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.002}, headers=me)
    assert r.json()["sharing"] is False  # positions after the end are not accepted
    with SessionLocal() as db:
        assert db.get(models.Walk, wid).last_lon == pytest.approx(START["lon"])


def test_revoke_makes_link_unusable_immediately(client):
    wid, me = start(client)
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "2468", "revoke": True}, headers=me).status_code == 200
    r = client.get(f"/api/walks/{wid}/contact")
    assert r.status_code == 410 and r.json()["detail"]["code"] == "revoked"


def test_link_expires_after_the_final_status_period(client):
    wid, me = start(client)
    client.post(f"/api/walks/{wid}/end", json={"pin": "2468"}, headers=me)
    with SessionLocal() as db:
        db.get(models.Walk, wid).ended_at = utcnow() - timedelta(hours=config.WALK_LINK_FINAL_HOURS, minutes=1)
        db.commit()
    r = client.get(f"/api/walks/{wid}/contact")
    assert r.status_code == 410 and r.json()["detail"]["code"] == "expired"


def test_inaccurate_gps_neither_fakes_movement_nor_raises_off_route(client):
    wid, me = start(client)
    for i in range(5):  # wild, inaccurate fixes far off the route
        client.post(f"/api/walks/{wid}/position", json={"lat": LAT + 0.002, "lon": LON + 0.0005 * i, "accuracy_m": 300}, headers=me)
    with SessionLocal() as db:
        w = db.get(models.Walk, wid)
        assert w.off_route_since is None and w.last_accuracy_m == 300
    tick(T["off_route_s"] + 1)
    s = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert s["trigger"] != "off_route"
    tick(T["stop_s"] + 2)  # inaccurate drift did not reset the "stopped" clock
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["trigger"] == "stopped"


def test_single_gps_jump_does_not_raise_off_route(client):
    wid, me = start(client)
    client.post(f"/api/walks/{wid}/position", json={"lat": LAT + 0.003, "lon": LON + 0.001, "accuracy_m": 10}, headers=me)  # jump
    client.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.0012, "accuracy_m": 10}, headers=me)  # back
    with SessionLocal() as db:
        assert db.get(models.Walk, wid).off_route_since is None


def test_short_signal_loss_does_not_alert(client):
    wid, me = start(client)
    tick(T["stop_s"] - 3)  # no positions for a while, but less than the stop period
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["asking"] is False


def test_repeated_sos_creates_one_police_alert(client):
    wid, me = start(client)
    for _ in range(4):
        assert client.post(f"/api/walks/{wid}/sos", headers=me).status_code == 200
    assert len(police_alerts_for(client, wid)) == 1
    events = client.get(f"/api/walks/{wid}/contact").json()["events"]
    assert sum("pressed SOS again" in e["text"] for e in events) == 3
    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 5)
    assert len(police_alerts_for(client, wid)) == 1  # the clock does not add another either
    s = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert s["trigger"] == "sos" and s["asking"]  # the walker sees the SOS state and can cancel with the walker's PIN
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "2468"}, headers=me).json()["status"] == "active"
    assert police_alerts_for(client, wid) == []


def test_duress_after_sos_does_not_duplicate_police_alert(client):
    wid, me = start(client)
    client.post(f"/api/walks/{wid}/sos", headers=me)
    client.post(f"/api/walks/{wid}/safe", json={"pin": "1357"}, headers=me)
    alerts = police_alerts_for(client, wid)
    assert len(alerts) == 1 and alerts[0]["duress"] is True


def test_wrong_pin_lockout_and_contacts_told(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    codes = [client.post(f"/api/walks/{wid}/safe", json={"pin": "0000"}, headers=me).status_code for _ in range(3)]
    assert codes == [403, 403, 403]
    locked = client.post(f"/api/walks/{wid}/safe", json={"pin": "2468"}, headers=me)
    assert locked.status_code == 429  # even the right PIN waits during the lock-out
    assert any("wrong PIN was entered" in e["text"] for e in client.get(f"/api/walks/{wid}/contact").json()["events"])
    with SessionLocal() as db:
        db.get(models.Walk, wid).pin_locked_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "2468"}, headers=me).status_code == 200


def test_pins_and_tokens_are_not_stored_in_plain_text(client):
    wid, me = start(client)
    with SessionLocal() as db:
        w = db.get(models.Walk, wid)
        assert "2468" not in (w.pin_hash or "") and "1357" not in (w.duress_pin_hash or "")
        assert me["X-Walk-Token"] not in (w.walker_token_hash or "")


def test_state_survives_a_restart(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    with TestClient(app) as fresh:  # a new server process reading the same database
        assert fresh.get(f"/api/walks/{wid}/state", headers=me).json()["asking"] is True
        assert fresh.post(f"/api/walks/{wid}/safe", json={"pin": "2468"}, headers=me).status_code == 200


def test_walk_nobody_ends_stops_sharing_and_is_deleted_later(client):
    wid, me = start(client)
    with SessionLocal() as db:
        db.get(models.Walk, wid).started_at = utcnow() - timedelta(hours=config.WALK_MAX_HOURS, minutes=1)
        db.commit()
    tick(0)
    c = client.get(f"/api/walks/{wid}/contact").json()
    assert c["status"] == "expired" and c["last"] is None
    with SessionLocal() as db:
        db.get(models.Walk, wid).ended_at = utcnow() - timedelta(hours=25)
        db.commit()
        retention.run(db, utcnow())
    with SessionLocal() as db:  # read back from the database itself
        w = db.get(models.Walk, wid)
        assert w.walker_name == "(deleted)" and w.walker_phone is None and w.last_lat is None
        assert db.scalar(select(func.count()).select_from(models.Contact).where(models.Contact.walk_id == wid)) == 0


def test_trip_data_not_in_public_map_or_street_endpoints(client):
    wid, me = start(client, name="Hidden Walker")
    for path in ("/api/map", "/api/summary", "/api/city/repairs"):
        assert "Hidden Walker" not in client.get(path).text and wid not in client.get(path).text
    with Session(engine) as db:
        sid = db.scalars(select(models.Street.id).where(models.Street.osm_way_id == 450001)).first()
    assert "Hidden Walker" not in client.get(f"/api/streets/{sid}").text
    assert "Hidden Walker" not in client.get(f"/api/streets/{sid}/observations").text
