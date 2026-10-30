"""Reads streets, places, photos and reports from the database and scores every street (blueprint §7)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import utcnow
from app.services.geo import point_to_line_m
from app.services.hours import status_at
from app.services.scoring import (
    HELP_RADIUS_M,
    MAX_PHOTOS_AVERAGED,
    NearbyPlace,
    Photo,
    PhotoFields,
    ReportIn,
    StreetScore,
    map_score,
    photo_score,
    street_score,
)

_DEG_200M = 0.0025  # ~250 m in degrees, a quick pre-filter before exact distances


@dataclass
class PlaceAt:
    place: models.Place
    status: str
    basis: str


COMMUNITY_PLACE_WINDOW_H = 3  # a "seen closed/open" report describes the place for 3 hours either side
IST_OFFSET = timedelta(hours=5, minutes=30)


def latest_place_reports(db: Session) -> dict[int, models.Report]:
    """Newest 'place closed' / 'place open' report for each place (blueprint §10: corrects hours until contradicted)."""
    out: dict[int, models.Report] = {}
    for r in db.scalars(select(models.Report).where(models.Report.kind.in_(["place_closed", "place_open"]),
                                                    models.Report.place_id.is_not(None)).order_by(models.Report.created_at)).all():
        out[r.place_id] = r
    return out


def place_status(p: models.Place, at: datetime, latest: dict[int, models.Report]) -> tuple[str, str]:
    """Status at walk time `at` (India time). A recent community report wins over listed hours; never assumed open."""
    r = latest.get(p.id)
    if r and abs((r.created_at + IST_OFFSET) - at) <= timedelta(hours=COMMUNITY_PLACE_WINDOW_H):
        return ("open" if r.kind == "place_open" else "closed"), "community"
    return status_at(p.opening_hours, p.category, at)


def places_at(db: Session, at: datetime) -> list[PlaceAt]:
    latest = latest_place_reports(db)
    out = []
    for p in db.scalars(select(models.Place)).all():
        status, basis = place_status(p, at, latest)
        out.append(PlaceAt(p, status, basis))
    return out


def _bbox(geometry: list[list[float]]) -> tuple[float, float, float, float]:
    lats, lons = [p[0] for p in geometry], [p[1] for p in geometry]
    return min(lats) - _DEG_200M, max(lats) + _DEG_200M, min(lons) - _DEG_200M, max(lons) + _DEG_200M


def score_streets(db: Session, at: datetime, now: datetime | None = None) -> dict[int, StreetScore]:
    """Score of every street for a walk at `at` (India time, decides open/closed).
    Photo and report ages are measured from `now` (UTC), i.e. how old the information is."""
    now = now or utcnow()
    places = places_at(db, at)

    photos: dict[int, list[Photo]] = {}
    for o in db.scalars(
        select(models.Observation)
        .where(models.Observation.analysis_status == "done", models.Observation.street_id.is_not(None))
        .order_by(models.Observation.captured_at.desc())
    ).all():
        lst = photos.setdefault(o.street_id, [])
        if len(lst) >= MAX_PHOTOS_AVERAGED:
            continue
        s = o.photo_score
        if s is None:
            s = photo_score(PhotoFields(o.lighting, o.people, o.open_places_count, o.vehicles, o.isolation, o.hazards))
        lst.append(Photo(s, (now - o.captured_at).total_seconds() / 60, o.lighting))

    reports: dict[int, list[ReportIn]] = {}
    for r in db.scalars(select(models.Report).where(models.Report.street_id.is_not(None))).all():
        reports.setdefault(r.street_id, []).append(ReportIn(r.kind, (now - r.created_at).total_seconds() / 60))

    out = {}
    for s in db.scalars(select(models.Street)).all():
        s0, s1, w0, w1 = _bbox(s.geometry)
        nearby = []
        for pa in places:
            p = pa.place
            if s0 <= p.lat <= s1 and w0 <= p.lon <= w1:
                d = point_to_line_m(p.lat, p.lon, s.geometry)
                if d <= HELP_RADIUS_M:
                    nearby.append(NearbyPlace(p.category, pa.status, d))
        out[s.id] = street_score(map_score(s.road_class, nearby), photos.get(s.id, []), reports.get(s.id, []))
    return out
