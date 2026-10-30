"""POST /api/route — shortest and safest walking routes with a comparison (blueprint §8)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db
from app.routers.map import parse_at
from app.services.geo import point_to_line_m
from app.services.routing import RouteError, Step, StreetEdge, path_length, plan, same_path
from app.services.scoring import StreetScore
from app.services.street_state import PlaceAt, places_at, score_streets

router = APIRouter(prefix="/api")


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    start: Point
    end: Point
    at: str | None = None  # India time of the walk, e.g. 2026-10-30T23:30; missing = now


def summarise(steps: list[Step], scores: dict[int, StreetScore], streets: dict[int, models.Street], places: list[PlaceAt]) -> dict:
    geometry: list[list[float]] = []
    for st in steps:
        g = st.geometry
        geometry.extend(g[1:] if geometry and geometry[-1] == g[0] else g)

    segments: list[dict] = []
    metres = {"green": 0.0, "yellow": 0.0, "red": 0.0}
    for st in steps:
        sc = scores[st.edge.street_id]
        metres[sc.colour] += st.edge.length_m
        if segments and segments[-1]["street_id"] == st.edge.street_id:
            segments[-1]["length_m"] += st.edge.length_m
            continue
        s = streets[st.edge.street_id]
        segments.append({
            "street_id": s.id,
            "name": s.name,
            "road_class": s.road_class,
            "length_m": st.edge.length_m,
            "score": sc.score,
            "colour": sc.colour,
            "freshest_photo_age_min": sc.freshest_photo_age_min,
        })
    for seg in segments:
        seg["length_m"] = round(seg["length_m"], 1)

    passed = []
    if geometry:
        lats, lons = [p[0] for p in geometry], [p[1] for p in geometry]
        pad = 0.001
        for pa in places:
            p = pa.place
            if min(lats) - pad <= p.lat <= max(lats) + pad and min(lons) - pad <= p.lon <= max(lons) + pad:
                d = point_to_line_m(p.lat, p.lon, geometry)
                if d <= config.SAFE_PLACE_PASSED_M:
                    passed.append({"id": p.id, "name": p.name, "category": p.category, "status": pa.status,
                                   "status_basis": pa.basis, "source": p.source, "distance_m": round(d)})

    ages = [scores[st.edge.street_id].freshest_photo_age_min for st in steps]
    ages = [a for a in ages if a is not None]
    distance = path_length(steps)
    return {
        "distance_m": round(distance),
        "duration_min": round(distance / (config.WALK_SPEED_KMH * 1000 / 60)),
        "metres_by_colour": {k: round(v) for k, v in metres.items()},
        "red_m": round(metres["red"]),
        "safe_places_passed": sum(1 for p in passed if p["status"] != "closed"),
        "places_passed": passed,
        "freshest_photo_age_min": min(ages) if ages else None,
        "segments": segments,
        "geometry": [[round(a, 7), round(b, 7)] for a, b in geometry],
    }


@router.post("/route")
def route(req: RouteRequest, db: Session = Depends(get_db)):
    at = parse_at(req.at)
    streets = {s.id: s for s in db.scalars(select(models.Street)).all()}
    if not streets:
        raise HTTPException(503, "No map data loaded. Run the map build step first.")
    scores = score_streets(db, at)
    edges = [StreetEdge(s.id, s.start_node, s.end_node, s.length_m, s.geometry) for s in streets.values()]
    try:
        pair = plan(edges, {k: v.score for k, v in scores.items()}, (req.start.lat, req.start.lon), (req.end.lat, req.end.lon))
    except RouteError as err:
        raise HTTPException(422, {"code": err.code, "message": err.message})

    places = places_at(db, at)
    shortest = summarise(pair.shortest, scores, streets, places)
    safest = summarise(pair.safest, scores, streets, places)
    identical = same_path(pair.shortest, pair.safest)

    notes = []
    if identical:
        notes.append("The safest route is the same as the shortest route: no other way through the mapped streets scores better.")
    if not pair.safest_within_limit:
        notes.append(
            f"The most cautious route would be more than {round((config.MAX_DETOUR_RATIO - 1) * 100)}% longer than the shortest, "
            "so this is the safest route within that limit."
        )
    if safest["red_m"] > 0:
        notes.append(
            f"This route still includes {safest['red_m']} m of red streets; no route within the detour limit avoids them. "
            "Consider the nearest safe spot or a cab."
        )
    if shortest["freshest_photo_age_min"] is None and safest["freshest_photo_age_min"] is None:
        notes.append("Scores come from map data only: no Sentinel photos of these streets yet.")

    return {
        "at": at.isoformat(timespec="minutes"),
        "start": {"requested": req.start.model_dump(), "snapped": pair.start.point, "snap_distance_m": round(pair.start.distance_m)},
        "end": {"requested": req.end.model_dump(), "snapped": pair.end.point, "snap_distance_m": round(pair.end.distance_m)},
        "shortest": shortest,
        "safest": safest,
        "same_route": identical,
        "safest_within_detour_limit": pair.safest_within_limit,
        "max_detour_ratio": config.MAX_DETOUR_RATIO,
        "notes": notes,
    }
