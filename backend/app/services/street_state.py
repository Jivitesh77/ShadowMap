"""Reads streets, places, photos and reports from the database and scores every street (blueprint §7)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
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


def retained_reports(now: datetime | None = None) -> tuple:
    """Query conditions for reports that may still be used: younger than REPORT_KEEP_DAYS and with a known time.
    Older ones (anonymised by services/retention.py) and malformed ones without a time never count anywhere."""
    cutoff = (now or utcnow()) - timedelta(days=config.REPORT_KEEP_DAYS)
    return (models.Report.created_at.is_not(None), models.Report.created_at >= cutoff)


def latest_place_reports(db: Session) -> dict[int, models.Report]:
    """Newest 'place closed' / 'place open' report for each place (blueprint §10: corrects hours until contradicted)."""
    out: dict[int, models.Report] = {}
    for r in db.scalars(select(models.Report).where(models.Report.kind.in_(["place_closed", "place_open"]),
                                                    models.Report.place_id.is_not(None), *retained_reports())
                        .order_by(models.Report.created_at)).all():
        out[r.place_id] = r
    return out


def place_status(p: models.Place, at: datetime, latest: dict[int, models.Report]) -> tuple[str, str]:
    """Status at walk time `at` (India time). A recent community report wins over listed hours; never assumed open."""
    r = latest.get(p.id)
    if r and abs((r.created_at + IST_OFFSET) - at) <= timedelta(hours=COMMUNITY_PLACE_WINDOW_H):
        return ("open" if r.kind == "place_open" else "closed"), "community"
    return status_at(p.opening_hours, p.category, at)


def places_at(db: Session, at: datetime, city: str | None = None) -> list[PlaceAt]:
    """Places with their status at the walk time. city=None means the default city (never all cities mixed)."""
    from app.services.cities import default_city
    latest = latest_place_reports(db)
    out = []
    for p in db.scalars(select(models.Place).where(models.Place.city == (city or default_city()))).all():
        status, basis = place_status(p, at, latest)
        out.append(PlaceAt(p, status, basis))
    return out


def _bbox(geometry: list[list[float]]) -> tuple[float, float, float, float]:
    lats, lons = [p[0] for p in geometry], [p[1] for p in geometry]
    return min(lats) - _DEG_200M, max(lats) + _DEG_200M, min(lons) - _DEG_200M, max(lons) + _DEG_200M


_NEARBY_CACHE: dict[str, tuple[tuple, dict[int, list[tuple[int, float]]]]] = {}


def _nearby_places(db: Session, city: str, streets: list[models.Street], places: list[models.Place]) -> dict[int, list[tuple[int, float]]]:
    """(place id, distance) of places within the help radius of each street. Depends only on geometry,
    so it is computed once per map build (the fingerprint changes when build_map replaces a city's rows)."""
    fingerprint = (len(streets), max((s.id for s in streets), default=0), round(sum(s.length_m for s in streets), 1),
                   len(places), max((p.id for p in places), default=0), round(sum(p.lat + p.lon for p in places), 6),
                   tuple(sorted({p.category for p in places})))
    cached = _NEARBY_CACHE.get(city)
    if cached and cached[0] == fingerprint:
        return cached[1]
    grid: dict[tuple[int, int], list[models.Place]] = {}  # places by ~280 m cell, so dense cities stay fast
    for p in places:
        grid.setdefault((int(p.lat // _DEG_200M), int(p.lon // _DEG_200M)), []).append(p)
    out: dict[int, list[tuple[int, float]]] = {}
    for s in streets:
        s0, s1, w0, w1 = _bbox(s.geometry)
        near = []
        for i in range(int(s0 // _DEG_200M), int(s1 // _DEG_200M) + 1):
            for j in range(int(w0 // _DEG_200M), int(w1 // _DEG_200M) + 1):
                for p in grid.get((i, j), []):
                    if s0 <= p.lat <= s1 and w0 <= p.lon <= w1:
                        d = point_to_line_m(p.lat, p.lon, s.geometry)
                        if d <= HELP_RADIUS_M:
                            near.append((p.id, d))
        out[s.id] = near
    _NEARBY_CACHE[city] = (fingerprint, out)
    return out


def score_streets(db: Session, at: datetime, city: str | None = None, now: datetime | None = None) -> dict[int, StreetScore]:
    """Score of every street of one city for a walk at `at` (India time, decides open/closed).
    Photo and report ages are measured from `now` (UTC), i.e. how old the information is."""
    from app.services.cities import default_city
    city = city or default_city()
    now = now or utcnow()
    places = {pa.place.id: pa for pa in places_at(db, at, city)}
    streets = db.scalars(select(models.Street).where(models.Street.city == city)).all()
    nearby_ids = _nearby_places(db, city, streets, [pa.place for pa in places.values()])

    photos: dict[int, list[Photo]] = {}
    for o in db.scalars(
        select(models.Observation)
        # Only analysed AND privacy-approved observations count (failed, pending, private ones never affect scores)
        .where(models.Observation.analysis_status == "done", models.Observation.photo_public.is_(True),
               models.Observation.street_id.is_not(None))
        .order_by(models.Observation.captured_at.desc())
    ).all():
        lst = photos.setdefault(o.street_id, [])
        if len(lst) >= MAX_PHOTOS_AVERAGED:
            continue
        s = o.photo_score
        if s is None:
            s = photo_score(PhotoFields(o.lighting, o.people, o.open_places_count, o.vehicles, o.isolation, o.hazards))
        lst.append(Photo(s, (now - o.captured_at).total_seconds() / 60, o.lighting, uncertain=o.confidence == "low"))

    reports: dict[int, list[ReportIn]] = {}
    for r in db.scalars(select(models.Report).where(models.Report.street_id.is_not(None), *retained_reports(now))).all():
        reports.setdefault(r.street_id, []).append(ReportIn(r.kind, (now - r.created_at).total_seconds() / 60))

    out = {}
    for s in streets:
        nearby = [NearbyPlace(places[pid].place.category, places[pid].status, d) for pid, d in nearby_ids.get(s.id, [])]
        out[s.id] = street_score(map_score(s.road_class, nearby), photos.get(s.id, []), reports.get(s.id, []))
    return out
