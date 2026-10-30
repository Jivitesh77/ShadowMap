"""Reaching the destination while "Are you safe?" is unanswered (agreed 2026-10-31): only an informational timeline
entry for contacts and police. It never answers the question, never resolves alerts, never restarts a finished walk,
and is recorded once per safety episode. Isolated test database; hand-made test lanes far from both real cities."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.main import app
from app.services import walks as W
from app.services.geo import line_length_m

T = config.WALK_TIMERS
POLICE = {"X-Police-Token": "test-police-code"}
LANES = {"guwahati": (59.0, 119.0, 880901), "delhi": (60.0, 120.0, 881001)}
NOTE = W.ARRIVAL_UNCONFIRMED


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 880901)).first():
            for city, (lat, lon, base) in LANES.items():
                pts = [[lat, lon + 0.001 * i] for i in range(6)]
                for i in range(5):
                    g = [pts[i], pts[i + 1]]
                    db.add(models.Street(osm_way_id=base + i, name=f"Arrival Lane {city}", road_type="residential", road_class="residential",
                                         start_node=base + i, end_node=base + i + 1, length_m=line_length_m(g), geometry=g, city=city))
            db.commit()
    with TestClient(app) as c:
        yield c


def start(c, city="guwahati", duress=False):
    lat, lon, _ = LANES[city]
    body = {"walker_name": "Kiran", "contacts": [{"name": "Friend"}], "pin": "1111", "city": city,
            "start": {"lat": lat, "lon": lon + 0.0001}, "end": {"lat": lat, "lon": lon + 0.0049}}
    if duress:
        body["duress_pin"] = "9999"
    r = c.post("/api/walks", json=body)
    assert r.status_code == 200, r.text
    return r.json()["walk_id"], {"X-Walk-Token": r.json()["walker_token"]}


def dest(city="guwahati"):
    lat, lon, _ = LANES[city]
    return {"lat": lat, "lon": lon + 0.0049, "accuracy_m": 8}


def away(city="guwahati"):
    lat, lon, _ = LANES[city]
    return {"lat": lat, "lon": lon + 0.002, "accuracy_m": 8}


def pos(c, wid, me, p):
    r = c.post(f"/api/walks/{wid}/position", json=p, headers=me)
    assert r.status_code == 200, r.text
    return r.json()


def tick(seconds):
    with SessionLocal() as db:
        W.evaluate_all(db, utcnow() + timedelta(seconds=seconds))


def state(wid):
    with SessionLocal() as db:
        w = db.get(models.Walk, wid)
        alerts = [(a.level, a.trigger, a.status) for a in db.scalars(select(models.Alert).where(models.Alert.walk_id == wid).order_by(models.Alert.id))]
        return w.status, w.escalation, [e["kind"] for e in w.events or []], alerts, (w.last_lat, w.last_lon)


def position_change(db, walk, p):
    """Exactly what POST /walks/{id}/position applies (routers/walks.py walk_position)."""
    def change():
        if walk.status in W.FINISHED:
            return
        W.update_position(db, walk, utcnow(), p["lat"], p["lon"], None, p["accuracy_m"])
        W.evaluate(db, walk, utcnow())
    return change


# ---------------- Normal arrival is unchanged ----------------

def test_arrival_without_a_prompt_ends_the_walk_as_before(client):
    wid, me = start(client)
    v = pos(client, wid, me, dest())
    assert v["status"] == "arrived" and v["sharing"] is False
    status, _, kinds, alerts, _ = state(wid)
    assert status == "arrived" and kinds.count("arrived") == 1 and NOTE not in kinds and alerts == []
    contact = client.get(f"/api/walks/{wid}/contact").json()
    assert contact["status"] == "arrived" and contact["last"] is None  # sharing stopped


# ---------------- Arrival during an unanswered prompt ----------------

def test_arrival_during_an_unanswered_prompt_is_only_noted(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)  # "Are you safe?" is asked
    v = pos(client, wid, me, dest())
    assert v["status"] == "checking" and v["asking"] is True and v["sharing"] is True  # still asking, still sharing
    status, escalation, kinds, alerts, last = state(wid)
    assert status == "checking" and escalation == 1 and kinds.count(NOTE) == 1 and "arrived" not in kinds and "safe" not in kinds
    assert alerts == [("ask", "stopped", "new")]  # the question is not resolved
    contact = client.get(f"/api/walks/{wid}/contact").json()
    note = next(e for e in contact["events"] if e["kind"] == NOTE)
    assert "does not mean the walker is safe" in note["text"] and contact["last"] == [dest()["lat"], dest()["lon"]]
    # the escalation clock carries on: contacts, then police
    tick(T["stop_s"] + T["ask_s"] + 2)
    tick(T["stop_s"] + T["ask_s"] + T["contacts_to_police_s"] + 5)
    status, escalation, _, alerts, _ = state(wid)
    assert status == "alert" and escalation == 3 and [a[0] for a in alerts] == ["ask", "contacts", "police"]
    # only the walker's PIN answers it
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me).json()["status"] == "active"
    assert all(a[2] == "resolved" for a in state(wid)[3])


def test_arrival_while_an_sos_is_open_keeps_the_police_alert(client):
    wid, me = start(client)
    client.post(f"/api/walks/{wid}/sos", headers=me)
    for _ in range(3):
        pos(client, wid, me, dest())
    status, escalation, kinds, alerts, _ = state(wid)
    assert status == "alert" and escalation == 3 and kinds.count(NOTE) == 1
    assert ("police", "sos", "new") in alerts and all(a[2] == "new" for a in alerts)
    police = [a for a in client.get("/api/police/alerts", params={"city": "guwahati"}, headers=POLICE).json()["alerts"] if a["walk_id"] == wid]
    assert len(police) == 1 and police[0]["status"] == "new" and police[0]["live_position"] == [dest()["lat"], dest()["lon"]]


def test_duress_stays_hidden_from_the_walker_after_arrival(client):
    wid, me = start(client, duress=True)
    tick(T["stop_s"] + 1)
    client.post(f"/api/walks/{wid}/safe", json={"pin": "9999"}, headers=me)  # duress: walker's screen looks normal
    v = pos(client, wid, me, dest())
    assert v["status"] == "active" and v["asking"] is False and "events" not in v  # nothing revealed on the walker's phone
    status, _, kinds, alerts, _ = state(wid)
    assert status == "alert" and kinds.count(NOTE) == 1 and any(a[1] == "duress" and a[2] == "new" for a in alerts)
    assert client.get(f"/api/walks/{wid}/contact").json()["duress"] is True


def test_repeated_fixes_add_one_note_per_safety_episode(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    for _ in range(6):
        pos(client, wid, me, dest())
    assert state(wid)[2].count(NOTE) == 1
    # the walker answers, walks back a bit, gets asked again and returns: one more note for the new episode
    assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me).status_code == 200
    pos(client, wid, me, away())
    tick(T["stop_s"] + 1)
    assert state(wid)[0] == "checking"
    for _ in range(4):
        pos(client, wid, me, dest())
    status, _, kinds, _, _ = state(wid)
    assert status == "checking" and kinds.count(NOTE) == 2 and kinds.count("check") == 2
    # once answered at the destination, the next fix is a normal arrival
    client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me)
    assert pos(client, wid, me, dest())["status"] == "arrived"
    assert state(wid)[2].count("arrived") == 1


def test_inaccurate_fix_near_the_destination_is_not_noted(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    pos(client, wid, me, {**dest(), "accuracy_m": 300})
    assert NOTE not in state(wid)[2]


# ---------------- Finished walks stay finished ----------------

def test_arrival_after_the_walk_ended_changes_nothing(client):
    wid, me = start(client)
    assert client.post(f"/api/walks/{wid}/end", json={"pin": "1111"}, headers=me).status_code == 200
    before = state(wid)
    v = pos(client, wid, me, dest())
    assert v["status"] == "ended" and v["sharing"] is False
    assert state(wid) == before  # no new events, no position stored
    assert client.get(f"/api/walks/{wid}/contact").json()["last"] is None


def test_arrival_after_expiry_changes_nothing(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)  # even with a prompt open when it expired
    with SessionLocal() as db:
        db.get(models.Walk, wid).started_at = utcnow() - timedelta(hours=config.WALK_MAX_HOURS, minutes=1)
        db.commit()
    tick(0)
    before = state(wid)
    assert before[0] == "expired"
    v = pos(client, wid, me, dest())
    assert v["status"] == "expired" and v["sharing"] is False and state(wid) == before


# ---------------- Simultaneous requests ----------------

def test_arrival_racing_a_pin_answer_that_wins(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    with SessionLocal() as stale:
        walk = stale.get(models.Walk, wid)  # the position request read the walk while it was still "checking"
        _ = walk.status, walk.events
        assert client.post(f"/api/walks/{wid}/safe", json={"pin": "1111"}, headers=me).status_code == 200  # PIN commits first
        W.save(stale, walk, position_change(stale, walk, dest()))  # re-applied to the newest (answered) state
    status, _, kinds, alerts, _ = state(wid)
    assert status == "arrived" and kinds[-2:] == ["safe", "arrived"] and NOTE not in kinds
    assert alerts == [("ask", "stopped", "resolved")]


def test_arrival_racing_a_pin_answer_that_loses(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    with SessionLocal() as stale:
        walk = stale.get(models.Walk, wid)  # the PIN request read the walk first
        _ = walk.status, walk.events
        pos(client, wid, me, dest())  # the arrival note commits first
        W.save(stale, walk, lambda: W.answer_check(stale, walk, utcnow(), "1111"))
    status, _, kinds, alerts, _ = state(wid)
    assert status == "active" and kinds.count(NOTE) == 1 and kinds[-1] == "safe"  # both kept, in order
    assert alerts == [("ask", "stopped", "resolved")]


def test_arrival_racing_an_sos(client):
    wid, me = start(client)
    tick(T["stop_s"] + 1)
    with SessionLocal() as stale:
        walk = stale.get(models.Walk, wid)
        _ = walk.status, walk.events
        client.post(f"/api/walks/{wid}/sos", headers=me)  # SOS commits first
        W.save(stale, walk, position_change(stale, walk, dest()))
    status, escalation, kinds, alerts, _ = state(wid)
    assert status == "alert" and escalation == 3 and "sos" in kinds and kinds.count(NOTE) == 1
    assert [a for a in alerts if a[0] == "police"] == [("police", "sos", "new")]

    wid2, me2 = start(client)  # the other order on an unprompted walk: arrival wins, the SOS comes after the end
    with SessionLocal() as stale:
        walk = stale.get(models.Walk, wid2)
        _ = walk.status, walk.events
        pos(client, wid2, me2, dest())
        W.save(stale, walk, lambda: W.sos(stale, walk, utcnow()))
    status, _, kinds, alerts, _ = state(wid2)
    assert status == "arrived" and kinds.count("arrived") == 1 and "sos_after_end" in kinds
    assert alerts == [("police", "sos_after_end", "new")]  # police alerted, walk stays finished (decision B)


# ---------------- City isolation ----------------

def test_arrival_note_in_delhi_stays_in_delhi(client):
    wid, me = start(client, "delhi")
    client.post(f"/api/walks/{wid}/sos", headers=me)
    pos(client, wid, me, dest("delhi"))
    assert state(wid)[2].count(NOTE) == 1
    delhi = [a["walk_id"] for a in client.get("/api/police/alerts", params={"city": "delhi"}, headers=POLICE).json()["alerts"]]
    guwahati = [a["walk_id"] for a in client.get("/api/police/alerts", params={"city": "guwahati"}, headers=POLICE).json()["alerts"]]
    assert wid in delhi and wid not in guwahati
