"""Route-use counters (city repair ranking, blueprint §11): one successful route request = +1 "planned" on each street of
the suggested route; one started walk = +1 "walked". Failures count nothing; concurrent requests lose nothing; each
city's streets have their own counters. Hand-made test lanes far from both real cities; isolated test database."""

import threading
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal, engine, init_db
from app.main import app
from app.routers.route import RouteRequest
from app.routers.route import route as route_endpoint
from app.services.geo import line_length_m

# ~550 m straight test lanes (5 pieces each). "race" is used only by the first-use concurrency test.
LANES = {"guwahati": (50.0, 110.0, 870001), "delhi": (51.0, 111.0, 870101), "race": (52.0, 112.0, 870201)}
CITY_OF = {"guwahati": "guwahati", "delhi": "delhi", "race": "guwahati"}


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 870001)).first():
            for key, (lat, lon, base) in LANES.items():
                pts = [[lat, lon + 0.001 * i] for i in range(6)]
                for i in range(5):
                    g = [pts[i], pts[i + 1]]
                    db.add(models.Street(osm_way_id=base + i, name=f"Use Lane {key}", road_type="residential", road_class="residential",
                                         start_node=base + i, end_node=base + i + 1, length_m=line_length_m(g), geometry=g, city=CITY_OF[key]))
            db.commit()
    with TestClient(app) as c:
        yield c


def ends(key):
    lat, lon, _ = LANES[key]
    return {"start": {"lat": lat, "lon": lon + 0.0001}, "end": {"lat": lat, "lon": lon + 0.0049}, "city": CITY_OF[key]}


def lane_ids(key):
    with Session(engine) as db:
        return set(db.scalars(select(models.Street.id).where(models.Street.name == f"Use Lane {key}")).all())


def counts(ids=None):
    """{street_id: (planned, walked)} for the given streets (all counter rows if None)."""
    with Session(engine) as db:
        q = select(models.RouteUse)
        if ids is not None:
            q = q.where(models.RouteUse.street_id.in_(ids))
        return {u.street_id: (u.planned or 0, u.walked or 0) for u in db.scalars(q).all()}


def totals():
    with Session(engine) as db:
        return tuple(db.execute(select(func.coalesce(func.sum(models.RouteUse.planned), 0),
                                       func.coalesce(func.sum(models.RouteUse.walked), 0))).one())


def delta(before, after, ids):
    return {i: (after.get(i, (0, 0))[0] - before.get(i, (0, 0))[0], after.get(i, (0, 0))[1] - before.get(i, (0, 0))[1]) for i in ids}


def route_street_ids(resp):
    return {s["street_id"] for s in resp["safest"]["segments"]}


def test_successful_route_counts_planned_once_on_each_suggested_street(client):
    ids = lane_ids("guwahati")
    before = counts(ids)
    r = client.post("/api/route", json=ends("guwahati"))
    assert r.status_code == 200
    on_route = route_street_ids(r.json())
    assert on_route <= ids and len(on_route) >= 3
    d = delta(before, counts(ids), ids)
    assert all(d[i] == ((1, 0) if i in on_route else (0, 0)) for i in ids), d


def test_repeated_routes_count_each_time(client):
    ids = lane_ids("guwahati")
    before = counts(ids)
    for _ in range(3):
        on_route = route_street_ids(client.post("/api/route", json=ends("guwahati")).json())
    d = delta(before, counts(ids), ids)
    assert all(d[i] == (3, 0) for i in on_route) and all(d[i] == (0, 0) for i in ids - on_route)


@pytest.mark.parametrize("body, status", [
    ({"start": {"lat": 50.0, "lon": 110.002}, "end": {"lat": 50.0, "lon": 110.002}}, 422),   # same place
    ({"start": {"lat": 50.0, "lon": 110.0001}, "end": {"lat": 50.5, "lon": 110.5}}, 422),    # destination off the map
    ({"start": {"lat": 51.0, "lon": 111.0001}, "end": {"lat": 51.0, "lon": 111.0049}, "city": "guwahati"}, 422),  # Delhi points, Guwahati map
    ({"start": {"lat": 50.0, "lon": 110.0001}, "end": {"lat": 50.0, "lon": 110.0049}, "city": "atlantis"}, 404),  # unknown city
    ({"start": {"lat": 95.0, "lon": 110.0}, "end": {"lat": 50.0, "lon": 110.0049}}, 422),     # invalid latitude
    ({"start": {"lat": 50.0, "lon": 110.0001}}, 422),                                          # destination missing
])
def test_failed_or_invalid_routes_count_nothing(client, body, status):
    before = totals()
    assert client.post("/api/route", json=body).status_code == status
    assert totals() == before


def test_briefing_is_not_a_second_planned_route(client):
    """The briefing recomputes the same route on the server; it must not count the route again."""
    before = totals()
    r = client.post("/api/route/briefing", json={**ends("guwahati"), "lang": "en"})
    assert r.status_code == 200
    assert totals() == before


def test_started_walk_counts_walked_once_and_failed_starts_count_nothing(client):
    ids = lane_ids("guwahati")
    body = {**ends("guwahati"), "walker_name": "Counter Test", "contacts": [{"name": "Friend"}], "pin": "1111"}
    before = counts(ids)
    r = client.post("/api/walks", json=body)
    assert r.status_code == 200
    d = delta(before, counts(ids), ids)
    walked = {i for i, v in d.items() if v == (0, 1)}
    assert len(walked) >= 3 and all(v == (0, 0) for i, v in d.items() if i not in walked), d  # walked once, never "planned"

    before_all = totals()
    assert client.post("/api/walks", json={**body, "duress_pin": "1111"}).status_code == 422  # same PINs: refused
    assert client.post("/api/walks", json={**body, "end": body["start"]}).status_code == 422  # no route: refused
    assert client.post("/api/walks", json={**body, "city": "delhi"}).status_code == 422  # wrong city's map
    assert totals() == before_all


def test_counters_are_city_specific(client):
    g_ids, d_ids = lane_ids("guwahati"), lane_ids("delhi")
    before_g, before_d = counts(g_ids), counts(d_ids)
    r = client.post("/api/route", json=ends("delhi"))
    assert r.status_code == 200 and route_street_ids(r.json()) <= d_ids
    assert counts(g_ids) == before_g  # Guwahati counters untouched
    assert any(v == (1, 0) for v in delta(before_d, counts(d_ids), d_ids).values())
    delhi = {i["name"]: i for i in client.get("/api/city/repairs", params={"city": "delhi"}).json()["items"]}
    guwahati = {i["name"]: i for i in client.get("/api/city/repairs", params={"city": "guwahati"}).json()["items"]}
    assert "Use Lane delhi" not in guwahati and "Use Lane guwahati" not in delhi  # (only reported streets are listed)


def _concurrent_routes(key, threads=8, per_thread=5):
    """Call the real /api/route handler from several threads at once, each with its own database session."""
    req = RouteRequest(**ends(key))
    go, errors, done = threading.Event(), [], Counter()

    def worker():
        go.wait()
        for _ in range(per_thread):
            with SessionLocal() as db:
                try:
                    route_endpoint(req, db)
                    done["ok"] += 1
                except Exception as e:  # reported by the assertion below
                    errors.append(repr(e))

    ts = [threading.Thread(target=worker) for _ in range(threads)]
    for t in ts:
        t.start()
    go.set()
    for t in ts:
        t.join(timeout=120)
    return done["ok"], errors


def test_concurrent_first_use_of_new_streets_loses_nothing(client):
    """No counter rows exist yet for this lane: many requests create them at the same moment."""
    ids = lane_ids("race")
    assert counts(ids) == {}
    ok, errors = _concurrent_routes("race")
    assert errors == [] and ok == 40
    got = counts(ids)
    on_route = {i for i, (p, _) in got.items() if p}
    assert len(on_route) >= 3 and all(got[i] == (40, 0) for i in on_route), got


def test_concurrent_requests_on_existing_counters_lose_nothing(client):
    ids = lane_ids("guwahati")
    before = counts(ids)
    ok, errors = _concurrent_routes("guwahati")
    assert errors == [] and ok == 40
    d = delta(before, counts(ids), ids)
    on_route = {i for i, v in d.items() if v != (0, 0)}
    assert len(on_route) >= 3 and all(d[i] == (40, 0) for i in on_route), d
