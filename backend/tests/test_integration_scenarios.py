"""End-to-end Walk With Me / city scenarios from the backend integration audit (2026-10-30), scenarios A-I.
Each test drives the whole workflow through the API on the isolated test database; time is moved with evaluate_all.
The last three tests reproduce defects found in the audit (docs/KNOWN_ISSUES.md #85-#87), now fixed; more detailed
regression tests are in test_walk_reliability.py."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.main import app
from app.services import retention
from app.services import walks as W
from app.services.geo import line_length_m

T = config.WALK_TIMERS
POLICE = {"X-Police-Token": "test-police-code"}
# Test-only street rows (~550 m straight lane per city) at coordinates no real map uses.
LINES = {"guwahati": (43.0, 103.0), "delhi": (44.0, 104.0)}


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 480001)).first():
            for k, (city, (lat, lon)) in enumerate(LINES.items()):
                pts = [[lat, lon + 0.001 * i] for i in range(6)]
                for i in range(5):
                    g = [pts[i], pts[i + 1]]
                    db.add(models.Street(osm_way_id=480001 + 10 * k + i, name=f"Scenario Lane {city}", road_type="residential",
                                         road_class="residential", start_node=480000 + 10 * k + i, end_node=480001 + 10 * k + i,
                                         length_m=line_length_m(g), geometry=g, city=city))
            db.commit()
    with TestClient(app) as c:
        yield c


def tick(seconds):
    with SessionLocal() as db:
        W.evaluate_all(db, utcnow() + timedelta(seconds=seconds))


def start(c, city="guwahati"):
    lat, lon = LINES[city]
    r = c.post("/api/walks", json={"walker_name": f"Walker {city}", "walker_phone": "+91 90000 00001", "city": city,
                                   "contacts": [{"name": "Contact A", "phone": "91000 00001"}, {"name": "Contact B"}],
                                   "pin": "1111", "duress_pin": "9999",
                                   "start": {"lat": lat, "lon": lon + 0.0001}, "end": {"lat": lat, "lon": lon + 0.0049}})
    assert r.status_code == 200, r.text
    return r.json()["walk_id"], {"X-Walk-Token": r.json()["walker_token"]}


def pos(c, wid, me, lat, lon):
    return c.post(f"/api/walks/{wid}/position", json={"lat": lat, "lon": lon, "accuracy_m": 8}, headers=me).json()


def police_for(c, city, wid, scope="active"):
    alerts = c.get("/api/police/alerts", params={"city": city, "scope": scope}, headers=POLICE).json()["alerts"]
    return [a for a in alerts if a["walk_id"] == wid]


def alert_rows(wid):
    with SessionLocal() as db:
        return [(a.level, a.status) for a in db.scalars(select(models.Alert).where(models.Alert.walk_id == wid)).all()]


def test_a_walk_to_destination_then_sharing_stops(client):
    wid, me = start(client)
    lat, lon = LINES["guwahati"]
    view = client.get(f"/api/walks/{wid}/contact").json()
    assert view["status"] == "active" and view["last"] is not None and "phone" not in str(view)
    for i in range(1, 5):
        assert pos(client, wid, me, lat, lon + 0.001 * i)["sharing"] is True
    arrived = pos(client, wid, me, lat, lon + 0.0049)
    assert arrived["status"] == "arrived" and arrived["sharing"] is False
    view = client.get(f"/api/walks/{wid}/contact").json()
    assert view["status"] == "arrived" and view["last"] is None and view["route"] is None
    assert pos(client, wid, me, lat, lon + 0.002)["status"] == "arrived"  # later positions are refused
    assert alert_rows(wid) == []


def test_b_off_route_escalates_ask_contacts_police(client):
    wid, me = start(client)
    lat, lon = LINES["guwahati"]
    pos(client, wid, me, lat + 0.002, lon + 0.001)  # ~220 m off the route
    tick(T["off_route_s"] + 1)
    state = client.get(f"/api/walks/{wid}/state", headers=me).json()
    assert state["asking"] and state["trigger"] == "off_route"
    tick(T["off_route_s"] + T["ask_s"] + 2)
    assert client.get(f"/api/walks/{wid}/contact").json()["escalation"] == 2
    tick(T["off_route_s"] + T["ask_s"] + T["contacts_to_police_s"] + 5)
    alerts = police_for(client, "guwahati", wid)
    assert len(alerts) == 1 and alerts[0]["trigger"] == "off_route"


def test_c_sos_once_then_police_workflow(client):
    wid, me = start(client)
    for _ in range(3):
        client.post(f"/api/walks/{wid}/sos", headers=me)
    [alert] = police_for(client, "guwahati", wid)
    for st in ("acknowledged", "unit_sent", "resolved"):
        r = client.post(f"/api/police/alerts/{alert['id']}/status", params={"city": "guwahati"}, json={"status": st}, headers=POLICE)
        assert r.status_code == 200
    again = client.post(f"/api/police/alerts/{alert['id']}/status", params={"city": "guwahati"}, json={"status": "acknowledged"}, headers=POLICE)
    assert again.status_code == 409  # no going backwards
    assert police_for(client, "guwahati", wid) == [] and police_for(client, "guwahati", wid, "history")[0]["status"] == "resolved"
    assert any("sent a unit" in e["text"] for e in client.get(f"/api/walks/{wid}/contact").json()["events"])


def test_d_duress_is_discreet_for_walker_but_visible_to_contacts_and_police(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    seen = client.post(f"/api/walks/{wid}/safe", json={"pin": "9999"}, headers=me).json()
    assert seen["ok"] and seen["status"] == "active" and seen["asking"] is False and seen["escalation"] == 0
    assert client.get(f"/api/walks/{wid}/contact").json()["duress"] is True
    assert police_for(client, "guwahati", wid)[0]["duress"] is True
    client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me)  # the real PIN cannot cancel duress
    assert len(police_for(client, "guwahati", wid)) == 1
    other, other_me = start(client)  # duress PIN at "end": walker sees "ended", sharing and alert continue
    assert client.post(f"/api/walks/{other}/end", json={"pin": "9999"}, headers=other_me).json()["status"] == "ended"
    assert client.get(f"/api/walks/{other}/contact").json()["status"] == "alert" and police_for(client, "guwahati", other)


def test_e_connection_loss_then_reconnect_without_duplicate_alerts(client):
    wid, me = start(client)
    lat, lon = LINES["guwahati"]
    tick(T["stop_s"] + 1)
    tick(T["stop_s"] + 2)  # the clock keeps running while the phone is silent: still one question
    assert alert_rows(wid) == [("ask", "new")]
    pos(client, wid, me, lat, lon + 0.002)  # back online
    assert client.get(f"/api/walks/{wid}/state", headers=me).json()["asking"]  # moving again is not an answer
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me).status_code == 200
    pos(client, wid, me, lat, lon + 0.003)
    tick(1)
    assert alert_rows(wid) == [("ask", "resolved")]


def test_f_two_walks_in_two_cities_stay_independent(client):
    g, g_me = start(client, "guwahati")
    d, d_me = start(client, "delhi")
    client.post(f"/api/walks/{d}/sos", headers=d_me)
    assert police_for(client, "delhi", d) and not police_for(client, "guwahati", d) and not police_for(client, "delhi", g)
    assert client.get(f"/api/walks/{g}/contact").json()["escalation"] == 0
    assert client.get(f"/api/walks/{d}/contact").json()["escalation"] == 3
    assert client.get(f"/api/walks/{d}/state", headers=g_me).status_code == 403
    assert client.get(f"/api/walks/{g}/contact").json()["last"][0] == LINES["guwahati"][0]
    assert client.get(f"/api/walks/{d}/contact").json()["last"][0] == LINES["delhi"][0]


def test_g_expired_walk_stops_sharing_and_is_anonymised(client):
    wid, me = start(client)
    with SessionLocal() as db:
        db.get(models.Walk, wid).started_at = utcnow() - timedelta(hours=config.WALK_MAX_HOURS, minutes=1)
        db.commit()
    tick(0)
    view = client.get(f"/api/walks/{wid}/contact").json()
    assert view["status"] == "expired" and view["last"] is None
    with SessionLocal() as db:
        db.get(models.Walk, wid).ended_at = utcnow() - timedelta(hours=25)
        db.commit()
        retention.run(db, utcnow())
    with SessionLocal() as db:
        w = db.get(models.Walk, wid)
        assert w.walker_name == "(deleted)" and w.walker_phone is None and not w.contacts and w.route == []


def test_h_report_changes_score_and_reaches_repair_list(client):
    lat, lon = LINES["delhi"]
    before = {s["id"]: s["score"] for s in client.get("/api/map", params={"city": "delhi"}).json()["streets"]}
    r = client.post("/api/reports", json={"kind": "broken_light", "lat": lat, "lon": lon + 0.0015, "device_id": "scenario-h", "city": "delhi"}).json()
    after = {s["id"]: s["score"] for s in client.get("/api/map", params={"city": "delhi"}).json()["streets"]}
    assert after[r["street_id"]] < before[r["street_id"]]
    assert any(i["street_id"] == r["street_id"] for i in client.get("/api/city/repairs", params={"city": "delhi"}).json()["items"])
    assert "Scenario Lane delhi" in client.get("/api/city/repairs.csv", params={"city": "delhi"}).text
    assert "Scenario Lane delhi" not in client.get("/api/city/repairs.csv", params={"city": "guwahati"}).text


def test_i_every_city_view_uses_the_selected_city(client):
    for city, other in (("guwahati", "delhi"), ("delhi", "guwahati")):
        names = {s["name"] for s in client.get("/api/map", params={"city": city}).json()["streets"]}
        assert f"Scenario Lane {city}" in names and f"Scenario Lane {other}" not in names
        lat, lon = LINES[city]
        assert client.post("/api/route", json={"city": city, "start": {"lat": lat, "lon": lon + 0.0001},
                                               "end": {"lat": lat, "lon": lon + 0.004}}).status_code == 200
        assert client.post("/api/route", json={"city": other, "start": {"lat": lat, "lon": lon + 0.0001},
                                               "end": {"lat": lat, "lon": lon + 0.004}}).status_code == 422


# ---------------- Defects found by the audit (fixed) ----------------

def test_correct_pin_after_arrival_does_not_restart_sharing(client):
    wid, me = start(client)
    lat, lon = LINES["guwahati"]
    pos(client, wid, me, lat, lon + 0.0049)
    client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me)
    assert client.get(f"/api/walks/{wid}/contact").json()["status"] == "arrived"


def test_sos_after_end_does_not_reopen_live_sharing(client):
    wid, me = start(client)
    client.post(f"/api/walks/{wid}/end", json={"pin": "1111"}, headers=me)
    client.post(f"/api/walks/{wid}/sos", headers=me)
    assert client.get(f"/api/walks/{wid}/contact").json()["status"] == "ended"
    assert len(police_for(client, "guwahati", wid)) == 1  # decision B: the police are still alerted


def test_clock_round_on_stale_walk_does_not_overwrite_concurrent_sos(client):
    wid, me = start(client)
    with SessionLocal() as monitor_db:
        walk = monitor_db.get(models.Walk, wid)  # the clock has loaded the walk...
        _ = walk.status, walk.events
        client.post(f"/api/walks/{wid}/sos", headers=me)  # ...the walker presses SOS meanwhile (committed)
        W.save(monitor_db, walk, lambda: W.tick(monitor_db, walk, utcnow() + timedelta(seconds=T["stop_s"] + 1)))
    with SessionLocal() as db:
        w = db.get(models.Walk, wid)
        assert w.escalation == 3 and any(e["kind"] == "sos" for e in w.events)
