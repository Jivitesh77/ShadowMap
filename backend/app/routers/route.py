"""POST /api/route — shortest and safest walking routes with a comparison (blueprint §8)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db
from app.rate_limit import rate_limit
from app.routers.map import parse_at
from app.services.geo import point_to_line_m
from app.services.routing import RouteError, Step, StreetEdge, path_length, plan, same_path
from app.services.scoring import StreetScore
from app.services import cities
from app.services.street_state import PlaceAt, places_at, score_streets

router = APIRouter(prefix="/api")
log = logging.getLogger("shadowmap.routes")


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    start: Point
    end: Point
    at: str | None = None  # India time of the walk, e.g. 2026-10-30T23:30; missing = now
    city: str | None = None  # demo city; default: the default city
    # False for automatic re-plans of a route the walker already asked for (time changed, scores refreshed): the repair
    # ranking counts each walker's planned route once, not every refresh. The route itself is the same either way.
    count: bool = True


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
                                   "status_basis": pa.basis, "sources": p.sources or [], "distance_m": round(d)})

    ages = [scores[st.edge.street_id].freshest_photo_age_min for st in steps]
    ages = [a for a in ages if a is not None]
    distance = path_length(steps)
    return {
        "distance_m": round(distance),
        "duration_min": round(distance / (config.WALK_SPEED_KMH * 1000 / 60)),
        "metres_by_colour": {k: round(v) for k, v in metres.items()},
        "red_m": round(metres["red"]),
        # Places within 50 m that are not known to be closed. Not a safety claim: being near a place proves nothing.
        "places_passed_not_closed": sum(1 for p in passed if p["status"] != "closed"),
        "places_passed": passed,
        "freshest_photo_age_min": min(ages) if ages else None,
        "segments": segments,
        "geometry": [[round(a, 7), round(b, 7)] for a, b in geometry],
    }


def count_route_use(db: Session, street_ids: set[int], field: str) -> None:
    """City repair ranking (blueprint §11): +1 `planned` or `walked` for each street, once per street.
    One INSERT … ON CONFLICT DO UPDATE statement: the database adds 1 to the stored value itself, so simultaneous
    requests can neither overwrite each other's count nor collide when a street's first counter row is created.
    Street ids belong to one city, so each city's counters stay separate."""
    if not street_ids:
        return
    column = getattr(models.RouteUse, field)
    stmt = sqlite_insert(models.RouteUse).values(
        [{"street_id": sid, "planned": int(field == "planned"), "walked": int(field == "walked")} for sid in sorted(street_ids)])
    db.execute(stmt.on_conflict_do_update(index_elements=[models.RouteUse.street_id], set_={field: func.coalesce(column, 0) + 1}))


def save_route_use(db: Session, street_ids: set[int], field: str) -> None:
    """Count and commit on its own. A database that stays locked too long costs this count (logged), never the
    route or walk the person asked for."""
    try:
        count_route_use(db, street_ids, field)
        db.commit()
    except OperationalError:
        db.rollback()
        log.warning("route-use counter not updated (%s, %d streets): database busy", field, len(street_ids))


def suggested_street_ids(result: dict) -> set[int]:
    return {seg["street_id"] for seg in result["safest"]["segments"]}


@router.post("/route", dependencies=[Depends(rate_limit("route"))])
def route(req: RouteRequest, db: Session = Depends(get_db)):
    """A route request the walker made: plan it, then count it once as "planned" (only when planning succeeded)."""
    result = plan_routes(req, db)
    if req.count:
        save_route_use(db, suggested_street_ids(result), "planned")
    return result


def plan_routes(req: RouteRequest, db: Session) -> dict:
    """Shortest and safest route with the comparison. Writes nothing (the briefing and walk start reuse it)."""
    at = parse_at(req.at)
    city = cities.resolve(req.city)
    streets = {s.id: s for s in db.scalars(select(models.Street).where(models.Street.city == city)).all()}
    if not streets:
        raise HTTPException(503, f"No map data loaded for {city}. Run the map build step first.")
    scores = score_streets(db, at, city)
    edges = [StreetEdge(s.id, s.start_node, s.end_node, s.length_m, s.geometry) for s in streets.values()]
    try:
        pair = plan(edges, {k: v.score for k, v in scores.items()}, (req.start.lat, req.start.lon), (req.end.lat, req.end.lon))
    except RouteError as err:
        raise HTTPException(422, {"code": err.code, "message": err.message})

    places = places_at(db, at, city)
    shortest = summarise(pair.shortest, scores, streets, places)
    safest = summarise(pair.safest, scores, streets, places)
    identical = same_path(pair.shortest, pair.safest)

    notes = []
    if identical:
        notes.append("The safest route is the same as the shortest route: no other way through the mapped streets scores better.")
    if pair.main_network_only:
        notes.append("A chosen point was nearest to a short path that does not connect to other mapped streets, "
                     "so the route starts or ends on the nearest connected street instead (see the snap distance).")
    if not pair.safest_within_limit:
        notes.append(
            f"The most cautious route would be more than {round((config.MAX_DETOUR_RATIO - 1) * 100)}% longer than the shortest, "
            "so this is the safest route within that limit."
        )
    if safest["red_m"] > 0:
        notes.append(
            f"This route still includes {safest['red_m']} m of red streets; no route within the detour limit avoids them. "
            "Consider going to the nearest open help point or taking a cab."
        )
    if shortest["freshest_photo_age_min"] is None and safest["freshest_photo_age_min"] is None:
        notes.append("Scores come from map data only: no Sentinel photos of these streets yet.")

    return {
        "city": city,
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
