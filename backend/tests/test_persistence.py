"""Data written to the database must still be there after the connection is closed and reopened."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import init_db, make_engine, utcnow


def test_rows_survive_reconnect(tmp_db_url):
    engine = make_engine(tmp_db_url)
    init_db(engine)
    with Session(engine) as db:
        street = models.Street(
            osm_way_id=1, name="Test Road", road_type="residential",
            start_node=10, end_node=11, length_m=120.5, geometry=[[26.0, 91.0], [26.001, 91.0]],
        )
        db.add(street)
        db.add(models.Place(osm_id="node/1", name="Test Pharmacy", category="pharmacy", lat=26.0, lon=91.0))
        db.flush()
        db.add(models.Observation(
            street_id=street.id, sentinel_label="Test #01", source="live",
            captured_at=utcnow(), lat=26.0005, lon=91.0, hazards=["none"],
        ))
        walk = models.Walk(
            id="walk-1", walker_name="Tester", route=[[26.0, 91.0], [26.001, 91.0]],
            dest_lat=26.001, dest_lon=91.0, pin_hash="x",
        )
        walk.contacts.append(models.Contact(name="Roommate", phone="000"))
        walk.alerts.append(models.Alert(level="ask", trigger="stopped"))
        db.add(walk)
        db.add(models.Report(street_id=street.id, kind="broken_light", lat=26.0, lon=91.0))
        db.commit()
    engine.dispose()  # fully close the database file

    engine2 = make_engine(tmp_db_url)
    with Session(engine2) as db:
        street = db.scalar(select(models.Street))
        assert street.name == "Test Road"
        assert street.geometry == [[26.0, 91.0], [26.001, 91.0]]
        assert street.observations[0].sentinel_label == "Test #01"
        assert street.reports[0].kind == "broken_light"
        assert db.scalar(select(models.Place)).category == "pharmacy"
        walk = db.get(models.Walk, "walk-1")
        assert [c.name for c in walk.contacts] == ["Roommate"]
        assert walk.alerts[0].status == "new"
    engine2.dispose()
