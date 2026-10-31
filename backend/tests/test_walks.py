"""Walk With Me end to end with three 'devices' (walker, trusted contact, police dashboard), time fast-forwarded."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.main import app
from app.services.geo import line_length_m
from app.services.walks import evaluate_all

LAT, LON = 31.0, 95.0  # this file's own street: 3 segments going east, ~285 m
PTS = [[LAT, LON], [LAT, LON + 0.001], [LAT, LON + 0.002], [LAT, LON + 0.003]]
START, END = {"lat": LAT, "lon": LON + 0.0001}, {"lat": LAT, "lon": LON + 0.0029}
T = config.WALK_TIMERS
POLICE = {"X-Police-Token": "test-police-code"}


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 660001)).first():
            for i in range(3):
                g = [PTS[i], PTS[i + 1]]
                db.add(models.Street(osm_way_id=660001 + i, name="Hostel Road", road_type="residential", road_class="residential",
                                     start_node=660000 + i, end_node=660001 + i, length_m=line_length_m(g), geometry=g))
            db.add(models.Place(osm_id="node/6601", name="Hostel Police Booth", category="police", lat=LAT + 0.0003, lon=LON + 0.0015,
                                sources=["osm"], in_demo_area=True))
            db.commit()
    with TestClient(app) as c:
        yield c


def start(client, **kw):
    body = {"walker_name": "Priya", "walker_phone": "+91 90000 00000", "contacts": [{"name": "Roommate", "phone": "90000 00001"}],
            "pin": "1234", "duress_pin": "9999", "start": START, "end": END, **kw}
    r = client.post("/api/walks", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    return d["walk_id"], {"X-Walk-Token": d["walker_token"]}


def tick(seconds: float):
    with SessionLocal() as db:
        evaluate_all(db, utcnow() + timedelta(seconds=seconds))


def contact(client, wid):
    return client.get(f"/api/walks/{wid}/contact").json()


def test_full_escalation_sequence_across_devices(client):
    wid, me = start(client)
    c = contact(client, wid)  # device 2: the roommate opens the trip link
    assert c["status"] == "active" and c["route"] and c["last"] and c["walker_name"] == "Priya"

    tick(T["stop_s"] - 2)
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["asking"] is False
    tick(T["stop_s"] + 1)  # standing still -> "Are you safe?"
    s = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert s["asking"] and s["trigger"] == "stopped"
    assert contact(client, wid)["alerts"] == []  # contacts are not alarmed yet, only told in the timeline
    assert client.get("/api/police/alerts", headers=POLICE).json()["alerts"] == [] or all(
        a["walk_id"] != wid for a in client.get("/api/police/alerts", headers=POLICE).json()["alerts"])

    tick(T["stop_s"] + T["ask_s"] + 2)  # no answer -> contacts alerted
    c = contact(client, wid)
    assert c["escalation"] == 2 and c["alerts"][-1]["level"] == "contacts" and c["last"] is not None
    assert any(e["kind"] == "alert_contacts" for e in c["events"])

    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 4)  # still nothing -> police dashboard
    alerts = [a for a in client.get("/api/police/alerts", headers=POLICE).json()["alerts"] if a["walk_id"] == wid]
    assert len(alerts) == 1
    a = alerts[0]
    assert a["trigger"] == "stopped" and a["live_position"] and a["route"] and a["walker_phone"] == "+91 90000 00000"

    # device 3: the control room works the alert
    for st in ("acknowledged", "unit_sent"):
        assert client.post(f"/api/police/alerts/{a['id']}/status", json={"status": st}, headers=POLICE).json()["status"] == st
    assert client.post(f"/api/police/alerts/{a['id']}/status", json={"status": "acknowledged"}, headers=POLICE).status_code == 409
    assert any("sent a unit" in e["text"] for e in contact(client, wid)["events"])

    # the walker answers: wrong PIN refused, right PIN resolves everything
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "0000"}, headers=me).status_code == 403
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1234"}, headers=me).json()["status"] == "active"
    assert client.get("/api/police/alerts", headers=POLICE).json()["alerts"] == [] or all(
        x["walk_id"] != wid for x in client.get("/api/police/alerts", headers=POLICE).json()["alerts"])
    hist = [x for x in client.get("/api/police/alerts?scope=history", headers=POLICE).json()["alerts"] if x["walk_id"] == wid][0]
    assert hist["status"] == "resolved" and hist["live_position"] is None and hist["route"] is None  # no tracking after
    assert [h["status"] for h in hist["history"]] == ["new", "acknowledged", "unit_sent", "resolved"]
    assert "False alarm" in contact(client, wid)["events"][-1]["text"]


def test_duress_pin_looks_like_cancel_but_escalates(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    r = client.post(f"/api/walks/{wid}/safe", json={"pin": "9999"}, headers=me)
    assert r.status_code == 200 and r.json()["ok"] is True
    s = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert s["status"] == "active" and s["asking"] is False and "duress" not in str(s).lower()  # walker's screen stays calm
    c = contact(client, wid)
    assert c["duress"] is True and c["escalation"] == 3
    assert any(a["walk_id"] == wid and a["duress"] and a["trigger"] == "duress"
               for a in client.get("/api/police/alerts", headers=POLICE).json()["alerts"])
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1234"}, headers=me).status_code == 200
    assert contact(client, wid)["duress"] is True  # the real PIN afterwards cannot quietly undo a duress alert


def test_sos_goes_straight_to_police(client):
    wid, me = start(client)
    assert client.post(f"/api/walks/{wid}/sos", headers=me).json()["ok"]
    assert any(a["walk_id"] == wid and a["trigger"] == "sos" for a in client.get("/api/police/alerts", headers=POLICE).json()["alerts"])
    assert contact(client, wid)["escalation"] == 3


def test_off_route_late_battery_and_arrival(client):
    wid, me = start(client)
    client.post(f"/api/walks/{wid}/position", json={"lat": LAT + 0.0009, "lon": LON + 0.001}, headers=me)  # ~100 m off the route
    tick(T["off_route_s"] + 1)
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["trigger"] == "off_route"
    client.post(f"/api/walks/{wid}/safe", json={"pin": "1234"}, headers=me)

    client.post(f"/api/walks/{wid}/position", json={"lat": LAT, "lon": LON + 0.0015, "battery_pct": 8}, headers=me)
    assert any(e["kind"] == "battery" for e in contact(client, wid)["events"])
    assert contact(client, wid)["alerts"][-1]["level"] == "info"  # told, not an alarm

    with SessionLocal() as db:  # pretend the walk has taken longer than planned
        w = db.get(models.Walk, wid)
        w.expected_arrival_at = utcnow() - timedelta(seconds=T["late_s"] + 1)
        w.last_moved_at = utcnow()
        db.commit()
    tick(0)
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["trigger"] == "late"
    client.post(f"/api/walks/{wid}/safe", json={"pin": "1234"}, headers=me)
    tick(1)
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["asking"] is False  # not asked again at once

    client.post(f"/api/walks/{wid}/position", json={"lat": END["lat"], "lon": END["lon"]}, headers=me)
    c = contact(client, wid)
    assert c["status"] == "arrived" and "phone reached the destination" in c["events"][-1]["text"] and "safe" not in c["events"][-1]["text"].lower() and c["last"] is None and c["route"] is None
    tick(T["stop_s"] + 60)
    assert contact(client, wid)["status"] == "arrived"  # no checks after arrival


def test_end_needs_pin_and_link_expires(client):
    wid, me = start(client)
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "1111"}, headers=me).status_code == 403
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "1234"}, headers=me).json()["status"] == "ended"
    assert contact(client, wid)["last"] is None
    with SessionLocal() as db:
        db.get(models.Walk, wid).ended_at = utcnow() - timedelta(hours=2)
        db.commit()
    assert client.get(f"/api/walks/{wid}/contact").status_code == 410


def test_only_the_right_device_can_act(client):
    wid, me = start(client)
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1234"}).status_code == 403  # contact link alone is not enough
    assert client.post(f"/api/walks/{wid}/sos", headers={"X-Walk-Token": "guess"}).status_code == 403
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "1234"}, headers={"X-Walk-Token": "guess"}).status_code == 403
    assert client.get("/api/police/alerts").status_code == 401
    assert client.get("/api/police/alerts", headers={"X-Police-Token": "x"}).status_code == 403
    assert client.post("/api/walks", json={"walker_name": "P", "contacts": [{"name": "R"}], "pin": "1234", "duress_pin": "1234",
                                            "start": START, "end": END}).json()["detail"]["code"] == "same_pins"
    assert client.post("/api/walks", json={"walker_name": "P", "contacts": [], "pin": "1234", "start": START, "end": END}).status_code == 422
    assert client.post("/api/walks", json={"walker_name": "P", "contacts": [{"name": "R"}], "pin": "12a4", "start": START, "end": END}).status_code == 422
    cfg = client.get("/api/walks/config").json()
    assert cfg["demo_mode"] is True and cfg["timers"]["stop_s"] == 15 and cfg["helplines"]["women"] == "181"


def test_where_am_i(client):
    r = client.post("/api/where-am-i", json={"lat": LAT, "lon": LON + 0.0015}).json()
    assert r["street"] == "Hostel Road" and r["nearest_police"]["name"] == "Hostel Police Booth"
    assert r["nearest_police"]["status"] == "unknown"  # no hours listed: never assumed open


def test_city_repair_list_and_csv(client):
    mid = (LAT, LON + 0.0005)
    for dev in ("city-a", "city-b"):
        client.post("/api/reports", json={"kind": "broken_light", "lat": mid[0], "lon": mid[1], "device_id": dev})
    items = client.get("/api/city/repairs").json()["items"]
    item = next(i for i in items if i["name"] == "Hostel Road" and i["broken_light_reports"] == 2)
    assert item["independent_reporters"] == 2 and item["nights_dark_last_7"] == 1 and item["walks_through"] >= 1
    assert item["rank"] >= 1 and "device" not in str(item).lower()
    csv = client.get("/api/city/repairs.csv")
    assert csv.headers["content-type"].startswith("text/csv") and csv.text.splitlines()[0].startswith("rank,street")
    assert "Hostel Road" in csv.text
