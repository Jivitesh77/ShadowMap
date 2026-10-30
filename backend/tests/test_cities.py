"""Two demo cities (IIIT Guwahati, Aastha Kunj Delhi): registry, switching, independent data, no cross-city leakage.
Uses the isolated test database (conftest). The small test streets here are hand-made test fixtures, placed far away
from both real cities so they cannot be mistaken for map data."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import engine, init_db
from app.main import app
from app.services import cities
from app.services.geo import haversine_m, line_length_m
from app.services.routing import StreetEdge, main_network, plan

# Test-only street rows: one short line per city, ~285 m east-west, at coordinates no real map uses.
CITY_LINES = {"guwahati": (40.0, 100.0), "delhi": (41.0, 101.0)}


def lane(lat, lon):
    return [[lat, lon], [lat, lon + 0.001], [lat, lon + 0.002], [lat, lon + 0.003]]


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 470001)).first():
            for k, (city, (lat, lon)) in enumerate(CITY_LINES.items()):
                pts = lane(lat, lon)
                for i in range(3):
                    g = [pts[i], pts[i + 1]]
                    db.add(models.Street(osm_way_id=470001 + 10 * k + i, name=f"Test Lane {city}", road_type="residential",
                                         road_class="residential", start_node=470000 + 10 * k + i, end_node=470001 + 10 * k + i,
                                         length_m=line_length_m(g), geometry=g, city=city))
                db.add(models.Place(name=f"Test Pharmacy {city}", category="pharmacy", lat=lat + 0.0002, lon=lon + 0.0015,
                                    opening_hours="24/7", sources=["test"], city=city))
            db.commit()
    with TestClient(app) as c:
        yield c


def ids(rows):
    return {r["id"] for r in rows}


# ---------------- Configuration ----------------

def test_registry_has_both_cities_and_guwahati_stays_default():
    assert cities.city_ids() == ["guwahati", "delhi"]
    assert cities.default_city() == "guwahati"
    assert cities.city_dir("guwahati") != cities.city_dir("delhi")


def test_delhi_area_covers_the_named_landmarks():
    area = json.loads((cities.city_dir("delhi") / "area.json").read_text())
    lat0, lon0 = area["center"]
    b = area["bbox"]
    # Aastha Kunj Park (OSM way 479658972) is the centre; the box reaches about 2 km (at least 1.95 km) in every direction.
    assert haversine_m(lat0, lon0, b["north"], lon0) >= 1950 and haversine_m(lat0, lon0, b["south"], lon0) >= 1950
    assert haversine_m(lat0, lon0, lat0, b["east"]) >= 1950 and haversine_m(lat0, lon0, lat0, b["west"]) >= 1950
    landmarks = {  # positions checked on OpenStreetMap (Nominatim) on 2026-10-30
        "Lotus Temple": (28.55336, 77.25861), "ISKCON (Sri Sri Radha Parthasarathi Mandir)": (28.55588, 77.25389),
        "Kalkaji Mandir": (28.54978, 77.26067), "Nehru Place": (28.54926, 77.25295), "East of Kailash": (28.5604, 77.2538),
    }
    for name, (lat, lon) in landmarks.items():
        assert b["south"] <= lat <= b["north"] and b["west"] <= lon <= b["east"], name


def test_unknown_city_is_a_clear_404_never_another_citys_data(client):
    for r in (client.get("/api/map", params={"city": "atlantis"}),
              client.post("/api/route", json={"city": "atlantis", "start": {"lat": 1, "lon": 1}, "end": {"lat": 1, "lon": 2}}),
              client.get("/api/city/repairs", params={"city": "atlantis"}),
              client.get("/api/summary", params={"city": "atlantis"})):
        assert r.status_code == 404 and r.json()["detail"]["code"] == "unknown_city"


def test_city_without_downloaded_osm_file_is_handled(tmp_path, monkeypatch):
    (tmp_path / "area.json").write_text(json.dumps({"center": [1, 2], "bbox": {"south": 0, "west": 1, "north": 2, "east": 3}}))
    monkeypatch.setattr(cities, "city_dir", lambda city: tmp_path)
    cities.map_source.cache_clear()
    try:
        src = cities.map_source("nowhere")
        assert src["file"] is None and src["area"]["center"] == [1, 2]
    finally:
        cities.map_source.cache_clear()

    from scripts import build_map
    monkeypatch.setattr(build_map, "DEMO_DATA", tmp_path)
    assert build_map.build_city("nowhere") == 0  # skipped with a message, nothing written


def test_guwahati_source_data_is_preserved():
    src = cities.map_source("guwahati")
    assert src["file"] and src["file"].startswith("osm_")
    assert (cities.city_dir("guwahati") / "manual_places.json").exists()


# ---------------- Switching and independence ----------------

def test_api_cities_lists_centre_and_bounds(client):
    d = client.get("/api/cities").json()
    assert d["default"] == "guwahati"
    by_id = {c["id"]: c for c in d["cities"]}
    assert set(by_id) == {"guwahati", "delhi"}
    for c in by_id.values():
        b = c["bbox"]
        assert b["south"] < c["center"][0] < b["north"] and b["west"] < c["center"][1] < b["east"]
    assert by_id["delhi"]["center"] != by_id["guwahati"]["center"]


def test_each_city_map_contains_only_its_own_streets_and_places(client):
    g = client.get("/api/map", params={"city": "guwahati"}).json()
    d = client.get("/api/map", params={"city": "delhi"}).json()
    assert g["source"]["city"] == "guwahati" and d["source"]["city"] == "delhi"
    assert not ids(g["streets"]) & ids(d["streets"]) and not ids(g["places"]) & ids(d["places"])
    assert any(s["name"] == "Test Lane delhi" for s in d["streets"]) and not any(s["name"] == "Test Lane delhi" for s in g["streets"])
    assert any(p["name"] == "Test Pharmacy guwahati" for p in g["places"]) and not any(p["name"] == "Test Pharmacy guwahati" for p in d["places"])
    default = client.get("/api/map").json()  # no city = Guwahati, as before multi-city
    assert ids(default["streets"]) == ids(g["streets"])


def test_street_detail_reports_its_city(client):
    d = client.get("/api/map", params={"city": "delhi"}).json()
    sid = next(s["id"] for s in d["streets"] if s["name"] == "Test Lane delhi")
    assert client.get(f"/api/streets/{sid}").json()["city"] == "delhi"


def test_routing_uses_only_the_chosen_citys_graph(client):
    lat, lon = CITY_LINES["delhi"]
    req = {"start": {"lat": lat, "lon": lon + 0.0001}, "end": {"lat": lat, "lon": lon + 0.0029}}
    r = client.post("/api/route", json={**req, "city": "delhi"})
    assert r.status_code == 200 and r.json()["city"] == "delhi"
    assert all(seg["name"] == "Test Lane delhi" for seg in r.json()["safest"]["segments"])
    other = client.post("/api/route", json={**req, "city": "guwahati"})  # Delhi points on the Guwahati graph
    assert other.status_code == 422 and other.json()["detail"]["code"] == "too_far"


def test_help_point_comes_from_the_chosen_city(client):
    lat, lon = CITY_LINES["delhi"]
    r = client.post("/api/help-point", json={"city": "delhi", "lat": lat, "lon": lon + 0.0005}).json()
    found = [r["best_open"]] + r["other_open"] + r["unknown_hours"] + r["outside_mapped_area"]
    names = {x["name"] for x in found if x}
    assert "Test Pharmacy delhi" in names and "Test Pharmacy guwahati" not in names


def test_reports_never_leak_into_the_other_city(client):
    lat, lon = CITY_LINES["delhi"]
    sent = client.post("/api/reports", json={"kind": "broken_light", "lat": lat, "lon": lon + 0.0015,
                                             "device_id": "city-test-1", "city": "delhi"})
    assert sent.status_code == 200 and sent.json()["city"] == "delhi"
    # The same spot reported "from" the Guwahati page does not attach to a Delhi street.
    wrong = client.post("/api/reports", json={"kind": "dark", "lat": lat, "lon": lon + 0.0015, "device_id": "city-test-2", "city": "guwahati"})
    assert wrong.status_code >= 400
    delhi_place = next(p for p in client.get("/api/map", params={"city": "delhi"}).json()["places"] if p["name"] == "Test Pharmacy delhi")
    wrong_place = client.post("/api/reports", json={"kind": "place_closed", "lat": lat, "lon": lon, "place_id": delhi_place["id"],
                                                    "device_id": "city-test-3", "city": "guwahati"})
    assert wrong_place.status_code >= 400

    delhi_repairs = client.get("/api/city/repairs", params={"city": "delhi"}).json()["items"]
    guwahati_repairs = client.get("/api/city/repairs", params={"city": "guwahati"}).json()["items"]
    assert any(i["name"] == "Test Lane delhi" for i in delhi_repairs)
    assert not any(i["name"] == "Test Lane delhi" for i in guwahati_repairs)
    assert "Test Lane delhi" not in client.get("/api/city/repairs.csv", params={"city": "guwahati"}).text
    assert client.get("/api/summary", params={"city": "delhi"}).json()["reports"] >= 1


def test_a_report_changes_only_its_own_citys_scores(client):
    g_before = {s["id"]: s["score"] for s in client.get("/api/map", params={"city": "guwahati"}).json()["streets"]}
    lat, lon = CITY_LINES["delhi"]
    client.post("/api/reports", json={"kind": "dark", "lat": lat, "lon": lon + 0.0005, "device_id": "city-test-4", "city": "delhi"})
    g_after = {s["id"]: s["score"] for s in client.get("/api/map", params={"city": "guwahati"}).json()["streets"]}
    assert g_before == g_after


# ---------------- Routing helper for dense OSM data ----------------

def test_route_falls_back_to_main_network_when_nearest_path_is_cut_off():
    lat, lon = 42.0, 102.0
    main = [StreetEdge(i + 1, i, i + 1, line_length_m(g), g)
            for i, g in enumerate([[[lat, lon + 0.001 * i], [lat, lon + 0.001 * (i + 1)]] for i in range(4)])]
    # a 20 m isolated footway 10 m north of the start, nearer than the main street (15 m south)
    island = StreetEdge(99, 900, 901, 0, [[lat + 0.00022, lon + 0.0004], [lat + 0.00022, lon + 0.0006]])
    island.length_m = line_length_m(island.geometry)
    streets = main + [island]
    assert {s.street_id for s in main_network(streets)} == {1, 2, 3, 4}
    pair = plan(streets, {}, (lat + 0.00013, lon + 0.0005), (lat, lon + 0.0035))
    assert pair.main_network_only and all(st.edge.street_id != 99 for st in pair.shortest)


# ---------------- Police dashboard: one city's control room sees only that city's alerts ----------------

POLICE = {"X-Police-Token": "test-police-code"}


def start_walk_in(client, city):
    lat, lon = CITY_LINES[city]
    r = client.post("/api/walks", json={"walker_name": f"Walker {city}", "contacts": [{"name": "Friend"}], "pin": "2468",
                                        "city": city, "start": {"lat": lat, "lon": lon + 0.0001},
                                        "end": {"lat": lat, "lon": lon + 0.0029}})
    assert r.status_code == 200, r.text
    wid, tok = r.json()["walk_id"], {"X-Walk-Token": r.json()["walker_token"]}
    assert client.post(f"/api/walks/{wid}/sos", headers=tok).status_code == 200  # SOS raises the police alert at once
    return wid


def police(client, city, scope="active"):
    r = client.get("/api/police/alerts", params={"scope": scope, "city": city}, headers=POLICE)
    assert r.status_code == 200 and r.json()["city"] == city
    return {a["walk_id"]: a for a in r.json()["alerts"]}


def test_police_alerts_are_listed_only_in_their_own_city(client):
    d_walk, g_walk = start_walk_in(client, "delhi"), start_walk_in(client, "guwahati")
    delhi, guwahati = police(client, "delhi"), police(client, "guwahati")
    assert d_walk in delhi and g_walk not in delhi
    assert g_walk in guwahati and d_walk not in guwahati
    assert d_walk not in police(client, "guwahati", "history") and g_walk not in police(client, "delhi", "history")
    default = client.get("/api/police/alerts", headers=POLICE).json()  # no city = Guwahati, as before
    assert default["city"] == "guwahati" and d_walk not in {a["walk_id"] for a in default["alerts"]}
    assert client.get("/api/police/alerts", params={"city": "atlantis"}, headers=POLICE).status_code == 404


def test_cross_city_status_update_is_rejected_and_changes_nothing(client):
    d_walk = start_walk_in(client, "delhi")
    alert = police(client, "delhi")[d_walk]
    r = client.post(f"/api/police/alerts/{alert['id']}/status", params={"city": "guwahati"}, json={"status": "resolved"}, headers=POLICE)
    assert r.status_code == 404
    r = client.post(f"/api/police/alerts/{alert['id']}/status", json={"status": "acknowledged"}, headers=POLICE)  # default city
    assert r.status_code == 404
    after = police(client, "delhi")[d_walk]
    assert after["status"] == "new" and after["history"] == alert["history"]


def test_status_workflow_still_works_inside_the_right_city(client):
    d_walk = start_walk_in(client, "delhi")
    aid = police(client, "delhi")[d_walk]["id"]
    for st in ("acknowledged", "unit_sent", "resolved"):
        r = client.post(f"/api/police/alerts/{aid}/status", params={"city": "delhi"}, json={"status": st}, headers=POLICE)
        assert r.status_code == 200 and r.json()["status"] == st
    assert d_walk not in police(client, "delhi")  # resolved: off the active list
    assert police(client, "delhi", "history")[d_walk]["status"] == "resolved"
    events = client.get(f"/api/walks/{d_walk}/contact").json()["events"]
    assert any("sent a unit" in e["text"] for e in events)


def test_police_coverage_counts_only_the_chosen_city(client):
    g = client.get("/api/police/coverage", params={"city": "guwahati"}, headers=POLICE).json()
    d = client.get("/api/police/coverage", params={"city": "delhi"}, headers=POLICE).json()
    with Session(engine) as db:
        for city, got in (("guwahati", g), ("delhi", d)):
            expected = db.scalar(select(func.count()).select_from(models.Street)
                                 .where(models.Street.city == city, models.Street.in_demo_area.is_(True)))
            assert got["streets_in_area"] == expected
