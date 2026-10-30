"""Community report retention (agreed policy: 30 days). After 30 days the device id and the tapped position are removed
(position 0.0 / 0.0 = removed) and the report no longer counts anywhere; type, street/place and time stay as history.
Isolated test database; hand-made test lanes and places far from both real cities."""

import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import config, models
from app.db import SessionLocal, engine, init_db, utcnow
from app.main import app
from app.services import retention
from app.services import walk_monitor as monitor_module
from app.services.geo import line_length_m
from app.services.street_state import latest_place_reports, place_status, score_streets

DAYS = config.REPORT_KEEP_DAYS
LANES = {"guwahati": (54.0, 114.0, 880401), "delhi": (55.0, 115.0, 880501)}


@pytest.fixture(scope="module")
def client():
    init_db()
    with Session(engine) as db:
        if not db.scalars(select(models.Street).where(models.Street.osm_way_id == 880401)).first():
            for city, (lat, lon, base) in LANES.items():
                g = [[lat, lon], [lat, lon + 0.002]]
                db.add(models.Street(osm_way_id=base, name=f"Retention Lane {city}", road_type="residential", road_class="residential",
                                     start_node=base, end_node=base + 1, length_m=line_length_m(g), geometry=g, city=city))
                db.add(models.Place(name=f"Retention Shop {city}", category="food_shop", lat=lat + 0.0002, lon=lon + 0.001,
                                    opening_hours="Mo-Su 08:00-22:00", sources=["test"], city=city))
            db.commit()
    with TestClient(app) as c:
        yield c


def street_id(city):
    with Session(engine) as db:
        return db.scalars(select(models.Street.id).where(models.Street.name == f"Retention Lane {city}")).one()


def place_id(city):
    with Session(engine) as db:
        return db.scalars(select(models.Place.id).where(models.Place.name == f"Retention Shop {city}")).one()


def add_report(city, age, kind="broken_light", place=False, device="dev-retention-1"):
    """A report `age` old (timedelta)."""
    lat, lon, _ = LANES[city]
    with SessionLocal() as db:
        r = models.Report(kind=kind, lat=lat + 0.00031, lon=lon + 0.00117, device_id=device,
                          street_id=None if place else street_id(city), place_id=place_id(city) if place else None,
                          created_at=utcnow() - age, fades_at=None)
        db.add(r)
        db.commit()
        return r.id


def row(rid):
    with SessionLocal() as db:
        r = db.get(models.Report, rid)
        return {"device_id": r.device_id, "lat": r.lat, "lon": r.lon, "kind": r.kind, "street_id": r.street_id,
                "place_id": r.place_id, "created_at": r.created_at}


def anonymised(rid):
    r = row(rid)
    return r["device_id"] is None and r["lat"] == 0.0 and r["lon"] == 0.0


def run_cleanup(now=None):
    with SessionLocal() as db:
        return retention.run(db, now or utcnow())


def test_reports_younger_than_30_days_stay_intact(client):
    young = [add_report("guwahati", timedelta(days=d)) for d in (0, 7, 29)] + [add_report("guwahati", timedelta(days=DAYS) - timedelta(minutes=5))]
    before = {rid: row(rid) for rid in young}
    run_cleanup()
    for rid in young:
        assert row(rid) == before[rid] and row(rid)["device_id"] == "dev-retention-1" and row(rid)["lat"] != 0.0


def test_reports_older_than_30_days_lose_device_and_position_but_keep_history(client):
    old = add_report("guwahati", timedelta(days=DAYS, minutes=5))
    very_old = add_report("guwahati", timedelta(days=400), kind="dark")
    place_old = add_report("guwahati", timedelta(days=45), kind="place_closed", place=True)
    before = {rid: row(rid) for rid in (old, very_old, place_old)}
    out = run_cleanup()
    assert out["reports_anonymised"] >= 3
    for rid in (old, very_old, place_old):
        after = row(rid)
        assert after["device_id"] is None and after["lat"] == 0.0 and after["lon"] == 0.0  # identifying data gone
        assert {k: after[k] for k in ("kind", "street_id", "place_id", "created_at")} == \
               {k: before[rid][k] for k in ("kind", "street_id", "place_id", "created_at")}  # history kept
    # nothing identifying anywhere in the stored row any more
    with SessionLocal() as db:
        stored = db.execute(text("SELECT device_id, lat, lon FROM reports WHERE id = :i"), {"i": old}).one()
    assert tuple(stored) == (None, 0.0, 0.0)


def test_a_report_without_a_time_cannot_be_stored(client):
    """Malformed rows without a time are impossible: the database refuses them (created_at is NOT NULL). The readers and
    the cleanup still treat a missing time as expired, as a second safeguard."""
    from sqlalchemy.exc import IntegrityError
    rid = add_report("guwahati", timedelta(0))
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE reports SET created_at = NULL WHERE id = :i"), {"i": rid})
            db.commit()
    assert row(rid)["created_at"] is not None


def test_expired_reports_never_affect_scores_lists_or_place_status(client):
    city = "delhi"
    sid, pid = street_id(city), place_id(city)
    with SessionLocal() as db:
        baseline = score_streets(db, utcnow(), city)[sid].score
    stale = add_report(city, timedelta(days=DAYS, hours=1), kind="broken_light", device="dev-old")
    stale_place = add_report(city, timedelta(days=DAYS, hours=1), kind="place_closed", place=True, device="dev-old")
    # Before any cleanup has run, the expired reports are already ignored everywhere:
    with SessionLocal() as db:
        assert score_streets(db, utcnow(), city)[sid].score == baseline
        when = (utcnow() - timedelta(days=DAYS, hours=1)) + timedelta(hours=5, minutes=30)  # the old report's own time (IST)
        place = db.get(models.Place, pid)
        assert pid not in latest_place_reports(db)
        assert place_status(place, when.replace(microsecond=0), latest_place_reports(db))[1] != "community"
    listed = {r["id"] for r in client.get("/api/reports", params={"place_id": pid}).json()["reports"]}
    listed |= {r["id"] for r in client.get("/api/reports", params={"street_id": sid}).json()["reports"]}
    assert stale not in listed and stale_place not in listed
    # A recent report still counts (the filter does not hide current information)
    fresh = add_report(city, timedelta(minutes=10), kind="broken_light", device="dev-new")
    with SessionLocal() as db:
        assert score_streets(db, utcnow(), city)[sid].score < baseline
    assert fresh in {r["id"] for r in client.get("/api/reports", params={"street_id": sid}).json()["reports"]}
    run_cleanup()
    assert anonymised(stale) and anonymised(stale_place) and not anonymised(fresh)


def test_cleanup_is_idempotent(client):
    rid = add_report("guwahati", timedelta(days=60))
    first = run_cleanup()
    assert first["reports_anonymised"] >= 1 and anonymised(rid)
    snapshot = row(rid)
    for _ in range(3):
        assert run_cleanup()["reports_anonymised"] == 0  # nothing left to change
    assert row(rid) == snapshot


def test_cleanup_follows_age_only_and_touches_nothing_else(client):
    old_g, old_d = add_report("guwahati", timedelta(days=31)), add_report("delhi", timedelta(days=31))
    young_d = add_report("delhi", timedelta(days=1), device="dev-delhi-young")
    lat, lon, _ = LANES["delhi"]
    with SessionLocal() as db:  # unrelated records that must not change
        walk = models.Walk(id="retention-walk-01", walker_name="Active Walker", walker_phone="+91 90000 00000", route=[[lat, lon]],
                           dest_lat=lat, dest_lon=lon, pin_hash="x$y", status="active", started_at=utcnow() - timedelta(days=40),
                           last_lat=lat, last_lon=lon, events=[], city="delhi")
        obs = models.Observation(street_id=street_id("delhi"), sentinel_label="Rider", source="live",
                                 captured_at=utcnow() - timedelta(days=40), lat=lat, lon=lon, device_id="sentinel-device-1",
                                 analysis_status="done")
        db.add_all([walk, obs])
        db.commit()
        obs_id = obs.id
    with Session(engine) as db:
        streets_before = db.scalar(text("SELECT COUNT(*) FROM streets"))
        places_before = db.scalar(text("SELECT COUNT(*) FROM places"))
    run_cleanup()
    assert anonymised(old_g) and anonymised(old_d)  # the same rule in every city
    assert row(young_d)["device_id"] == "dev-delhi-young" and row(young_d)["lat"] != 0.0  # young report in the other city kept
    with SessionLocal() as db:
        w = db.get(models.Walk, "retention-walk-01")
        assert w.walker_name == "Active Walker" and w.last_lat == lat and w.status == "active"  # running walk untouched
        o = db.get(models.Observation, obs_id)
        assert o.device_id == "sentinel-device-1" and o.lat == lat  # Sentinel records are not report data
        assert db.scalar(text("SELECT COUNT(*) FROM streets")) == streets_before
        assert db.scalar(text("SELECT COUNT(*) FROM places")) == places_before


def test_rate_limit_and_duplicate_checks_still_work_for_recent_reports(client):
    lat, lon, _ = LANES["guwahati"]
    body = {"kind": "dark", "lat": lat, "lon": lon + 0.001, "device_id": "dev-ratecheck", "city": "guwahati"}
    assert client.post("/api/reports", json=body).status_code == 200
    run_cleanup()
    assert client.post("/api/reports", json=body).status_code == 409  # duplicate still recognised after cleanup


def test_interrupted_cleanup_leaves_nothing_half_done_and_finishes_after_restart(client, monkeypatch):
    rids = [add_report("guwahati", timedelta(days=35), device=f"dev-crash-{i}") for i in range(3)]
    with SessionLocal() as db:  # the server stops after the update ran but before it was saved
        assert retention.anonymise_expired_reports(db, utcnow()) >= 3
        db.rollback()
    assert not any(anonymised(r) for r in rids)  # all or nothing: no half-anonymised rows
    engine.dispose()  # "restart": new database connections
    # On start the background clock runs the cleanup in its first round, by itself.
    monkeypatch.setattr(monitor_module, "evaluate_all", lambda db, now: None)  # only the cleanup part is under test here
    clock = monitor_module.WalkMonitor(every_s=0.05)
    clock.start()
    try:
        for _ in range(100):
            if all(anonymised(r) for r in rids):
                break
            time.sleep(0.05)
    finally:
        clock.stop()
        clock._thread.join(timeout=10)  # no round may run after this test's patches are undone
    assert all(anonymised(r) for r in rids)
