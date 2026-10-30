from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models
from app.db import engine, init_db
from app.main import app


def test_route_api_success_and_errors():
    init_db()
    with Session(engine) as db:  # a lone 222 m street far from other test data
        db.add(models.Street(osm_way_id=77, name="API Test Rd", road_type="residential", road_class="residential",
                             start_node=7001, end_node=7002, length_m=222.4, geometry=[[27.0, 92.0], [27.002, 92.0]]))
        db.commit()
    with TestClient(app) as client:
        ok = client.post("/api/route", json={"start": {"lat": 27.0002, "lon": 92.0}, "end": {"lat": 27.0018, "lon": 92.0},
                                             "at": "2026-10-29T23:30"})
        assert ok.status_code == 200
        body = ok.json()
        assert 170 < body["shortest"]["distance_m"] < 180  # 0.0016 deg of latitude = ~178 m
        assert body["shortest"]["duration_min"] == 2
        assert body["same_route"] is True  # only one street: no invented alternative
        assert body["safest"]["segments"][0]["colour"] == "yellow"  # residential map score 45
        assert any("same as the shortest" in n for n in body["notes"])

        far = client.post("/api/route", json={"start": {"lat": 27.0002, "lon": 92.0}, "end": {"lat": 27.05, "lon": 92.0}})
        assert far.status_code == 422 and far.json()["detail"]["code"] == "too_far"
        bad = client.post("/api/route", json={"start": {"lat": 200, "lon": 92.0}, "end": {"lat": 27.0, "lon": 92.0}})
        assert bad.status_code == 422
        missing = client.post("/api/route", json={"start": {"lat": 27.0, "lon": 92.0}})
        assert missing.status_code == 422
