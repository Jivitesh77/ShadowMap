from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.db import engine, init_db
from app.main import app
from app.services.geo import haversine_m, point_to_line_m
from app.services.osm import place_category, road_class
from scripts.build_map import split_ways


def test_road_classes_follow_blueprint():
    assert road_class({"highway": "trunk"}) == "main"
    assert road_class({"highway": "tertiary"}) == "main"
    assert road_class({"highway": "residential"}) == "residential"
    assert road_class({"highway": "footway"}) == "lane"
    assert road_class({"highway": "footway", "tunnel": "yes"}) == "underpass"


def test_place_categories():
    assert place_category({"amenity": "police"}) == "police"
    assert place_category({"shop": "chemist"}) == "pharmacy"
    assert place_category({"highway": "bus_stop"}) == "transit"
    assert place_category({"amenity": "parking"}) is None


def test_ways_split_at_junctions():
    a = {"id": 1, "nodes": [1, 2, 3], "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001}, {"lat": 0, "lon": 0.002}]}
    b = {"id": 2, "nodes": [2, 4], "geometry": [{"lat": 0, "lon": 0.001}, {"lat": 0.001, "lon": 0.001}]}
    segs = split_ways([a, b])
    assert sorted((s["start_node"], s["end_node"]) for s in segs) == [(1, 2), (2, 3), (2, 4)]


def test_distances():
    assert 110 < haversine_m(26.0, 91.0, 26.001, 91.0) < 112
    assert 99 < point_to_line_m(26.0009, 91.0005, [[26.0, 91.0], [26.0, 91.001]]) < 101


def test_map_endpoint_returns_streets_places_and_status():
    init_db()
    with Session(engine) as db:
        db.add(models.Street(osm_way_id=9, name="Test Rd", road_type="tertiary", road_class="main",
                             start_node=1, end_node=2, length_m=111, geometry=[[26.0, 91.0], [26.001, 91.0]]))
        db.add(models.Place(osm_id="node/9", name="Test Police", category="police", lat=26.0005, lon=91.0003))
        db.commit()
    with TestClient(app) as client:
        body = client.get("/api/map", params={"at": "2026-10-29T23:30"}).json()
        assert body["at"] == "2026-10-29T23:30"
        assert any(s["name"] == "Test Rd" for s in body["streets"])
        police = next(p for p in body["places"] if p["name"] == "Test Police")
        assert (police["status"], police["status_basis"]) == ("unknown", "missing")
        street_id = next(s["id"] for s in body["streets"] if s["name"] == "Test Rd")
        detail = client.get(f"/api/streets/{street_id}").json()
        assert detail["nearby_places"][0]["name"] == "Test Police"
        assert client.get("/api/map", params={"at": "not-a-time"}).status_code == 400
        assert client.get("/api/streets/999999").status_code == 404


def test_manual_places_need_verifier_and_date(tmp_path, monkeypatch):
    import json

    import pytest

    import scripts.build_map as bm

    monkeypatch.setattr(bm, "DEMO_DATA", tmp_path)
    bbox = {"south": 26.07, "west": 91.55, "north": 26.09, "east": 91.57}
    entry = {"name": "Checked Pharmacy", "category": "pharmacy", "lat": 26.08, "lon": 91.56,
             "opening_hours": "Mo-Su 08:00-22:00", "verified_by": "Field lead", "verified_on": "2026-10-31", "note": "On site"}
    (tmp_path / "manual_places.json").write_text(json.dumps({"places": [entry]}))
    [p] = bm.build_manual_places(bbox)
    assert (p.source, p.verified_by, p.in_demo_area, p.osm_id) == ("manual", "Field lead", True, None)

    (tmp_path / "manual_places.json").write_text(json.dumps({"places": [{**entry, "verified_by": ""}]}))
    with pytest.raises(SystemExit):
        bm.build_manual_places(bbox)
    (tmp_path / "manual_places.json").write_text(json.dumps({"places": [{**entry, "category": "temple"}]}))
    with pytest.raises(SystemExit):
        bm.build_manual_places(bbox)
