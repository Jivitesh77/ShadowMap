"""Walker features: community reports, briefing (incl. AI fact check), nearest help point, observations."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import engine, init_db, utcnow
from app.main import app
from app.services import briefing, gemini

LAT, LON = 30.0, 94.0  # this file's own small network, far from other tests
o = 0.0001  # detour ~11 m south
NODES = {"A": (0, 0), "B": (0, 0.001), "C": (0, 0.002), "D": (-o, 0), "E": (-o, 0.001), "F": (-o, 0.002)}
EDGES = [  # (id suffix, from, to, class, name)
    (1, "A", "B", "residential", "Top Lane"), (2, "B", "C", "residential", "Top Lane"),
    (3, "A", "D", "main", "Link Road"), (4, "D", "E", "main", "Bottom Road"), (5, "E", "F", "main", "Bottom Road"),
    (6, "F", "C", "main", "Link Road"),
]
START = {"lat": LAT, "lon": LON + 0.0001}
END = {"lat": LAT, "lon": LON + 0.0019}
NODE_ID = {k: 770000 + i for i, k in enumerate(NODES)}


def pt(n):
    return [LAT + NODES[n][0], LON + NODES[n][1]]


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 770001)).first():
            from app.services.geo import line_length_m
            for sid, a, b, cls, name in EDGES:
                g = [pt(a), pt(b)]
                db.add(models.Street(osm_way_id=770000 + sid, name=name, road_type="residential", road_class=cls,
                                     start_node=NODE_ID[a], end_node=NODE_ID[b], length_m=line_length_m(g), geometry=g))
            db.add_all([
                models.Place(osm_id="node/7701", name="Night Chemist", category="pharmacy", lat=LAT - o, lon=LON + 0.0015,
                             opening_hours="24/7", sources=["osm"], in_demo_area=True),
                models.Place(osm_id="node/7702", name="Corner Tea", category="food_shop", lat=LAT + 0.00005, lon=LON + 0.0005,
                             sources=["osm"], in_demo_area=True),
                models.Place(osm_id="node/7703", name="Far Police Post", category="police", lat=LAT + 0.02, lon=LON,
                             sources=["osm"], in_demo_area=False),
                models.Place(osm_id="node/7704", name="Apollo Pharmacy", category="pharmacy", lat=LAT + 0.5, lon=LON,
                             sources=["osm"], in_demo_area=False),  # exists elsewhere: the AI must not mention it here
            ])
            db.commit()
    with TestClient(app) as c:
        yield c


def report(client, kind, lat, lon, device, place_id=None):
    return client.post("/api/reports", json={"kind": kind, "lat": lat, "lon": lon, "device_id": device, "place_id": place_id})


def safest_streets(client):
    r = client.post("/api/route", json={"start": START, "end": END}).json()
    return {s["name"] for s in r["safest"]["segments"]}, r


def test_reports_change_scores_and_the_route(client):
    names, _ = safest_streets(client)
    assert names == {"Top Lane"}  # residential 45 vs main 60 detour: the short way wins at first

    mid_ab = (LAT, LON + 0.0005)
    with Session(engine) as db:
        ab = db.scalars(select(models.Street).where(models.Street.osm_way_id == 770001)).one().id
    before = next(s["score"] for s in client.get("/api/map").json()["streets"] if s["id"] == ab)
    r1 = report(client, "dark", *mid_ab, "dev-walk-1")
    assert r1.status_code == 200 and r1.json()["street_name"] == "Top Lane" and r1.json()["effect_points"] == -15
    assert r1.json()["street_score_now"] == before - 15  # blueprint §10: "dark here" -15
    assert report(client, "dark", *mid_ab, "dev-walk-1").status_code == 409  # same person cannot agree with themselves
    r2 = report(client, "dark", *mid_ab, "dev-walk-2")
    assert r2.json()["street_score_now"] == before - 22.5  # two people within an hour count more: -15 x 1.5
    report(client, "dark", LAT, LON + 0.0015, "dev-walk-1")
    report(client, "dark", LAT, LON + 0.0015, "dev-walk-2")

    names, r = safest_streets(client)
    assert "Bottom Road" in names and not r["same_route"]  # reports now route people around Top Lane
    listed = client.get("/api/reports", params={"street_id": r1.json()["street_id"]}).json()["reports"]
    assert {x["kind"] for x in listed} == {"dark"} and all("device_id" not in x for x in listed)


def test_report_limits_and_validation(client):
    assert report(client, "felt_unsafe", LAT + 0.01, LON, "dev-x").json()["detail"]["code"] == "not_near_street"
    assert report(client, "bad_kind", LAT, LON, "dev-x").json()["detail"]["code"] == "bad_kind"
    assert report(client, "place_closed", LAT, LON, "dev-x").json()["detail"]["code"] == "no_place"
    for i, kind in enumerate(["dark", "deserted", "felt_unsafe", "well_lit", "broken_light"]):
        assert report(client, kind, LAT - o, LON + 0.0005, "dev-limit").status_code == 200, i
    assert report(client, "dark", LAT - o, LON + 0.0015, "dev-limit").status_code == 429  # 6th in an hour


def test_place_report_overrides_hours_near_the_report_time(client):
    with Session(engine) as db:
        chemist = db.scalars(select(models.Place).where(models.Place.name == "Night Chemist")).one()
    assert report(client, "place_closed", chemist.lat, chemist.lon, "dev-place", chemist.id).status_code == 200
    places = {p["name"]: p for p in client.get("/api/map").json()["places"]}
    assert places["Night Chemist"]["status"] == "closed" and places["Night Chemist"]["status_basis"] == "community"
    far_future = (utcnow() + timedelta(hours=5, minutes=30) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M")
    later = {p["name"]: p for p in client.get("/api/map", params={"at": far_future}).json()["places"]}
    assert later["Night Chemist"]["status"] == "open" and later["Night Chemist"]["status_basis"] == "listed"


def test_briefing_without_ai_uses_only_route_data(client, monkeypatch):
    monkeypatch.setattr(gemini, "configured", lambda: False)
    b = client.post("/api/route/briefing", json={"start": START, "end": END, "lang": "en"}).json()
    assert b["source"] == "data" and "not set up" in b["note"]
    assert "km" in b["text"] and "map data only" in b["text"]
    assert "Apollo" not in b["text"] and "Far Police" not in b["text"]
    assert 4 <= len(b["sentences"]) <= 6
    hi = client.post("/api/route/briefing", json={"start": START, "end": END, "lang": "hi"}).json()
    assert hi["lang"] == "hi" and "किलोमीटर" in hi["text"]
    assert client.post("/api/route/briefing", json={"start": START, "end": END, "lang": "fr"}).status_code == 422


def _ai_answer(texts):
    return {"sentences": [{"text": t, "fact_ids": ["W"]} for t in texts]}


GOOD = ["Your route is about {km} km.", "I don't have fresh photos; this is map data only.",
        "Part of it runs on {street}.", "Nothing here is confirmed open."]


def test_ai_briefing_is_fact_checked(client, monkeypatch):
    monkeypatch.setattr(gemini, "configured", lambda: True)
    facts = client.post("/api/route/briefing", json={"start": START, "end": END}).json()["facts"]
    km = f"{facts['walk']['distance_m'] / 1000:.1f}"
    street = next(seg["name"] for seg in facts["segments"] if seg["name"])  # a street that IS on this route
    good = [t.replace("{km}", km).replace("{street}", street) for t in GOOD]

    monkeypatch.setattr(gemini, "generate_json", lambda system, prompt: _ai_answer(good))
    b = client.post("/api/route/briefing", json={"start": START, "end": END}).json()
    assert b["source"] == "ai" and b["text"].startswith(f"Your route is about {km} km")

    for bad in (["Apollo Pharmacy is open on your way."],  # a real place, but not on this route
                ["A rider saw it 7 minutes ago."],  # an observation age that is not in the facts
                ["This route is safe."]):  # never "safe"
        monkeypatch.setattr(gemini, "generate_json", lambda system, prompt, bad=bad: _ai_answer(good[:3] + bad))
        b = client.post("/api/route/briefing", json={"start": START, "end": END}).json()
        assert b["source"] == "data" and "fact check" in b["note"], bad

    def broken(system, prompt):
        raise gemini.GeminiError("Gemini returned HTTP 500")
    monkeypatch.setattr(gemini, "generate_json", broken)
    b = client.post("/api/route/briefing", json={"start": START, "end": END}).json()
    assert b["source"] == "data" and "AI unavailable" in b["note"]


def test_check_rejects_bad_citations():
    facts = {"walk": {"id": "W", "distance_m": 300}, "segments": [{"id": "S1", "name": "Top Lane"}], "places": []}
    assert briefing.check_ai_text([{"text": "Top Lane is lit.", "fact_ids": ["S9"]}] * 3, facts, set(), "en")
    assert not briefing.check_ai_text([{"text": "Top Lane ahead.", "fact_ids": ["S1"]}] * 3, facts, {"top lane"}, "en")


def test_nearest_help_point_never_treats_unknown_as_open(client):
    with Session(engine) as db:  # remove the community "closed" report from the earlier test so listed hours apply
        for r in db.scalars(select(models.Report).where(models.Report.kind == "place_closed")).all():
            db.delete(r)
        db.commit()
    res = client.post("/api/help-point", json={"lat": LAT, "lon": LON + 0.0002}).json()
    assert res["best_open"]["name"] == "Night Chemist" and res["best_open"]["status"] == "open"
    assert res["best_open"]["walk_m"] > 0 and len(res["best_open"]["geometry"]) >= 2
    assert [p["name"] for p in res["unknown_hours"]] == ["Corner Tea"]  # nearer, but hours unknown: listed separately
    assert res["outside_mapped_area"][0]["name"] == "Far Police Post"  # beyond mapped streets: straight-line only


def test_street_observations_endpoint(client):
    with Session(engine) as db:
        sid = db.scalars(select(models.Street).where(models.Street.osm_way_id == 770001)).one().id
    assert client.get(f"/api/streets/{sid}/observations").json() == {"observations": []}
    assert client.get("/api/streets/99999999/observations").status_code == 404
