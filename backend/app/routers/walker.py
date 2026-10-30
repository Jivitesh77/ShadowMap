"""Walker features: street observations, AI route briefing, nearest help point (blueprint §6, §8, §10)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, utcnow
from app.routers.map import parse_at
from app.routers.route import Point, RouteRequest, route as compute_route
from app.services.briefing import make_briefing, build_facts
from app.services.geo import haversine_m
from app.services.routing import RouteError, StreetEdge, path_length, plan
from app.services.scoring import REPORT_EFFECTS
from app.services.street_state import places_at, score_streets

router = APIRouter(prefix="/api")


def _age_min(t) -> float:
    return round((utcnow() - t).total_seconds() / 60, 1)


@router.get("/streets/{street_id}/observations")
def street_observations(street_id: int, db: Session = Depends(get_db)):
    """Latest Sentinel observations of one street. Photos are not included: they are shown only after blurring (M6)."""
    if not db.get(models.Street, street_id):
        raise HTTPException(404, "Street not found.")
    rows = db.scalars(select(models.Observation).where(models.Observation.street_id == street_id)
                      .order_by(models.Observation.captured_at.desc()).limit(10)).all()
    return {"observations": [{
        "id": o.id,
        "captured_age_min": _age_min(o.captured_at),
        "captured_at_utc": o.captured_at.isoformat() + "Z",
        "sentinel_label": o.sentinel_label,
        "source": o.source,
        "position_source": o.position_source,
        "analysis_status": o.analysis_status,
        "lighting": o.lighting,
        "streetlights_visible": o.streetlights_visible,
        "streetlights_working": o.streetlights_working,
        "people": o.people,
        "open_places_count": o.open_places_count,
        "vehicles": o.vehicles,
        "isolation": o.isolation,
        "hazards": o.hazards,
        "description": o.description,
        "confidence": o.confidence,
        "photo_available": False,
        "photo_note": "Photos are shown only after faces and number plates are blurred (coming next).",
    } for o in rows]}


class BriefingRequest(RouteRequest):
    lang: str = Field("en", pattern="^(en|hi)$")


@router.post("/route/briefing")
def route_briefing(req: BriefingRequest, db: Session = Depends(get_db)):
    """Briefing for the safest route. The route is recalculated here, so the briefing only uses server-side data."""
    r = compute_route(RouteRequest(start=req.start, end=req.end, at=req.at), db)
    ids = {seg["street_id"] for seg in r["safest"]["segments"]}
    names = {s.id: s.name for s in db.scalars(select(models.Street).where(models.Street.id.in_(ids))).all()}

    observations: dict[int, dict] = {}
    for o in db.scalars(select(models.Observation).where(models.Observation.street_id.in_(ids),
                                                        models.Observation.analysis_status == "done")
                        .order_by(models.Observation.captured_at.desc())).all():
        observations.setdefault(o.street_id, {"age_min": _age_min(o.captured_at), "lighting": o.lighting, "people": o.people,
                                              "open_places": o.open_places_count, "description": o.description,
                                              "sentinel": o.sentinel_label})
    reports: dict[int, list[dict]] = {}
    now = utcnow()
    for rep in db.scalars(select(models.Report).where(models.Report.street_id.in_(ids))).all():
        age = (now - rep.created_at).total_seconds() / 60
        if rep.kind in REPORT_EFFECTS and age <= REPORT_EFFECTS[rep.kind][1]:
            reports.setdefault(rep.street_id, []).append({"kind": rep.kind, "age_min": round(age)})

    facts = build_facts(r["safest"], r["shortest"], r["same_route"], r["at"], observations, reports, names)
    gazetteer = {n.lower() for n in db.scalars(select(models.Street.name)).all() if n}
    gazetteer |= {n.lower() for n in db.scalars(select(models.Place.name)).all() if n}
    b = make_briefing(facts, req.lang, gazetteer)
    return {**b, "lang": req.lang, "facts": facts, "model": config.GEMINI_MODEL if b["source"] == "ai" else None}


class HelpRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    at: str | None = None


@router.post("/help-point")
def nearest_help_point(req: HelpRequest, db: Session = Depends(get_db)):
    """Nearest place open at the walk time, reached along mapped streets (blueprint §10 "nearest safe spot").
    Places with unknown hours are listed separately and never presented as open."""
    at = parse_at(req.at)
    streets = db.scalars(select(models.Street)).all()
    edges = [StreetEdge(s.id, s.start_node, s.end_node, s.length_m, s.geometry) for s in streets]
    scores = {k: v.score for k, v in score_streets(db, at).items()}
    reachable, outside = [], []
    for pa in places_at(db, at):
        p = pa.place
        if pa.status == "closed":
            continue
        straight = haversine_m(req.lat, req.lon, p.lat, p.lon)
        if straight > 5000:
            continue
        try:
            pair = plan(edges, scores, (req.lat, req.lon), (p.lat, p.lon))
        except RouteError as err:
            if err.code == "too_far":  # the place (or the person) is beyond the mapped walking streets
                outside.append({"id": p.id, "name": p.name, "category": p.category, "status": pa.status,
                                "straight_line_m": round(straight)})
                continue
            if err.code == "same_place":
                pair = None
            else:
                continue
        length = path_length(pair.safest) if pair else 0.0
        geometry = []
        if pair:
            for st in pair.safest:
                g = st.geometry
                geometry.extend(g[1:] if geometry and geometry[-1] == g[0] else g)
        reachable.append({"id": p.id, "name": p.name, "category": p.category, "status": pa.status, "status_basis": pa.basis,
                          "walk_m": round(length), "walk_min": round(length / (config.WALK_SPEED_KMH * 1000 / 60)),
                          "geometry": geometry})
    reachable.sort(key=lambda x: x["walk_m"])
    open_now = [x for x in reachable if x["status"] == "open"]
    unknown = [x for x in reachable if x["status"] == "unknown"][:3]
    for x in unknown:
        x.pop("geometry")
    outside.sort(key=lambda x: x["straight_line_m"])
    best = open_now[0] if open_now else None
    if best:
        message = None
    elif unknown:
        message = "No place known to be open at this time can be reached on mapped streets. The nearest places below have unknown hours — they may be closed."
    else:
        message = "No place can be reached on mapped streets from here. Use the help numbers if you need help."
    return {"at": at.isoformat(timespec="minutes"), "best_open": best, "other_open": [{k: v for k, v in x.items() if k != "geometry"} for x in open_now[1:3]],
            "unknown_hours": unknown, "outside_mapped_area": outside[:3], "message": message}
