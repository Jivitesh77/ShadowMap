"""Map data for the screens: streets, places and their open/closed/unknown status at a chosen time."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db, utcnow
from app.rate_limit import rate_limit
from app.services.geo import haversine_m, point_to_line_m
from app.services.places import confidence
from app.services.scoring import StreetScore
from app.services import cities
from app.services.street_state import latest_place_reports, place_status, score_streets

router = APIRouter(prefix="/api")

IST = timezone(timedelta(hours=5, minutes=30))  # India has one time zone and no daylight saving


@router.get("/cities")
def list_cities(db: Session = Depends(get_db)):
    """Demo cities the user can switch between, with their map centre and bounds."""
    out = []
    for c in cities.registry()["cities"]:
        area = (cities.map_source(c["id"]).get("area") or {})
        streets = db.scalar(select(func.count()).select_from(models.Street).where(models.Street.city == c["id"]))
        out.append({"id": c["id"], "name": c["name"], "center": area.get("center"), "bbox": area.get("bbox"),
                    "has_map_data": bool(streets)})
    return {"default": cities.default_city(), "cities": out}


def parse_at(at: str | None) -> datetime:
    """`at` is India time like 2026-10-30T23:30. Missing = now."""
    if not at:
        return datetime.now(IST).replace(tzinfo=None, second=0, microsecond=0)
    try:
        return datetime.fromisoformat(at).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "Time must look like 2026-10-30T23:30 (India time).")


def place_out(p: models.Place, at: datetime, center: list[float] | None, community: dict | None = None) -> dict:
    status, basis = place_status(p, at, community or {})
    report = (community or {}).get(p.id)
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
        "community_report": ({"kind": report.kind, "created_at_utc": report.created_at.isoformat() + "Z"} if report else None),
        "distance_from_center_m": round(haversine_m(center[0], center[1], p.lat, p.lon)) if center else None,
    }


# Place fields that depend on the walk time or on recent community reports (everything else is fixed per map build).
PLACE_DYNAMIC = {"status", "status_basis", "community_report", "confidence", "confidence_reason"}


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


@router.get("/map", dependencies=[Depends(rate_limit("map"))])
def get_map(at: str | None = Query(None, description="India time, e.g. 2026-10-30T23:30"),
            city: str | None = Query(None, description="demo city id; default: the default city"),
            view: str = Query("full", pattern="^(full|scores)$",
                              description="full = streets with shapes + places; scores = only what changes over time"),
            db: Session = Depends(get_db)):
    when = parse_at(at)
    city = cities.resolve(city)
    source = {**cities.map_source(city), "city": city, "centre_label": cities.centre_label(city)}
    center = (source.get("area") or {}).get("center")
    streets = db.scalars(select(models.Street).where(models.Street.city == city)).all()
    places = db.scalars(select(models.Place).where(models.Place.city == city)).all()
    scores = score_streets(db, when, city)
    community = latest_place_reports(db)
    generated = utcnow().isoformat(timespec="seconds") + "Z"  # when these scores were computed (shown as data age)
    if view == "scores":
        # Street shapes and place details never change between map builds: the app keeps them from the full load and
        # refreshes only scores and open / closed status (Delhi: ~3 MB -> a small fraction).
        return {
            "at": when.isoformat(timespec="minutes"),
            "generated_utc": generated,
            "city": city,
            "view": "scores",
            "streets": [{"id": s.id, **score_out(scores.get(s.id))} for s in streets],
            "places": [{k: v for k, v in place_out(p, when, center, community).items() if k in PLACE_DYNAMIC} | {"id": p.id}
                       for p in places],
        }
    return {
        "at": when.isoformat(timespec="minutes"),
        "generated_utc": generated,
        "view": "full",
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
        "places": [place_out(p, when, center, community) for p in places],
    }


@router.get("/streets/{street_id}")
def get_street(street_id: int, at: str | None = None, db: Session = Depends(get_db)):
    s = db.get(models.Street, street_id)
    if not s:
        raise HTTPException(404, "Street not found.")
    when = parse_at(at)
    center = (cities.map_source(s.city).get("area") or {}).get("center")
    nearby = []
    community = latest_place_reports(db)
    for p in db.scalars(select(models.Place).where(models.Place.city == s.city)).all():
        d = point_to_line_m(p.lat, p.lon, s.geometry)
        if d <= 200:
            nearby.append({**place_out(p, when, center, community), "distance_m": round(d)})
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
        **score_out(score_streets(db, when, s.city).get(s.id)),
        "city": s.city,
        "observations": observations,
        "reports": reports,
        "nearby_places": nearby,
    }
