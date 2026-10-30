"""Map data for the screens: streets, places and their open/closed/unknown status at a chosen time."""

import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.services.geo import haversine_m, point_to_line_m
from app.services.hours import status_at
from app.services.places import confidence
from app.services.scoring import StreetScore
from app.services.street_state import score_streets

router = APIRouter(prefix="/api")

IST = timezone(timedelta(hours=5, minutes=30))  # India has one time zone and no daylight saving
DEMO_DATA = Path(__file__).resolve().parents[3] / "assets" / "demo-data"


@lru_cache
def map_source() -> dict:
    """Area and download details of the saved OpenStreetMap file the map was built from."""
    files = sorted(DEMO_DATA.glob("osm_*.json"))
    if not files:
        return {}
    meta = json.loads(files[-1].read_text()).get("shadowmap", {})
    return {
        "file": files[-1].name,
        "downloaded_at_utc": meta.get("downloaded_at_utc"),
        "osm_data_timestamp": meta.get("osm_data_timestamp"),
        "licence": meta.get("licence"),
        "area": meta.get("area"),
    }


def parse_at(at: str | None) -> datetime:
    """`at` is India time like 2026-10-30T23:30. Missing = now."""
    if not at:
        return datetime.now(IST).replace(tzinfo=None, second=0, microsecond=0)
    try:
        return datetime.fromisoformat(at).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "Time must look like 2026-10-30T23:30 (India time).")


def place_out(p: models.Place, at: datetime, center: list[float] | None) -> dict:
    status, basis = status_at(p.opening_hours, p.category, at)
    level, reason = confidence(p.sources or [], p.name, p.verified_on, p.osm_last_edited, datetime.now(IST).date())
    return {
        "id": p.id,
        "osm_id": p.osm_id,
        "name": p.name,
        "category": p.category,
        "lat": p.lat,
        "lon": p.lon,
        "opening_hours": p.opening_hours,
        "hours_source": p.hours_source,
        "phone": p.phone,
        "status": status,
        "status_basis": basis,
        "sources": p.sources or [],
        "osm_last_edited": p.osm_last_edited,
        "duplicate_osm_ids": p.duplicate_osm_ids or [],
        "in_demo_area": p.in_demo_area,
        "verified_by": p.verified_by,
        "verified_on": p.verified_on,
        "note": p.note,
        "match_note": p.match_note,
        "confidence": level,
        "confidence_reason": reason,
        "distance_from_center_m": round(haversine_m(center[0], center[1], p.lat, p.lon)) if center else None,
    }


def score_out(sc: StreetScore | None) -> dict:
    if sc is None:
        return {"score": None, "colour": None}
    return {
        "score": sc.score,
        "colour": sc.colour,
        "map_score": sc.map_score,
        "photo_score": sc.photo_score,
        "photo_weight": sc.weight,
        "report_adjustment": sc.report_adjustment,
        "freshest_photo_age_min": sc.freshest_photo_age_min,
    }


@router.get("/map")
def get_map(at: str | None = Query(None, description="India time, e.g. 2026-10-30T23:30"), db: Session = Depends(get_db)):
    when = parse_at(at)
    source = map_source()
    center = (source.get("area") or {}).get("center")
    streets = db.scalars(select(models.Street)).all()
    places = db.scalars(select(models.Place)).all()
    scores = score_streets(db, when)
    return {
        "at": when.isoformat(timespec="minutes"),
        "source": source,
        "streets": [
            {
                "id": s.id,
                "name": s.name,
                "road_type": s.road_type,
                "road_class": s.road_class,
                "lit": s.lit,
                "length_m": s.length_m,
                "geometry": s.geometry,
                "osm_way_id": s.osm_way_id,
                **score_out(scores.get(s.id)),
            }
            for s in streets
        ],
        "places": [place_out(p, when, center) for p in places],
    }


@router.get("/streets/{street_id}")
def get_street(street_id: int, at: str | None = None, db: Session = Depends(get_db)):
    s = db.get(models.Street, street_id)
    if not s:
        raise HTTPException(404, "Street not found.")
    when = parse_at(at)
    center = (map_source().get("area") or {}).get("center")
    nearby = []
    for p in db.scalars(select(models.Place)).all():
        d = point_to_line_m(p.lat, p.lon, s.geometry)
        if d <= 200:
            nearby.append({**place_out(p, when, center), "distance_m": round(d)})
    nearby.sort(key=lambda p: p["distance_m"])
    observations = db.scalar(select(func.count()).select_from(models.Observation).where(models.Observation.street_id == s.id))
    reports = db.scalar(select(func.count()).select_from(models.Report).where(models.Report.street_id == s.id))
    return {
        "id": s.id,
        "name": s.name,
        "road_type": s.road_type,
        "road_class": s.road_class,
        "lit": s.lit,
        "length_m": s.length_m,
        "osm_way_id": s.osm_way_id,
        **score_out(score_streets(db, when).get(s.id)),
        "observations": observations,
        "reports": reports,
        "nearby_places": nearby,
    }
