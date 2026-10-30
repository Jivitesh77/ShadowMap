"""One-tap community reports (blueprint §10). No free text, by design: reports describe the street, never people."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import get_db, utcnow
from app.routers.map import parse_at
from app.services.geo import locate_on_line
from app.services.scoring import REPORT_EFFECTS
from app.services.street_state import score_streets

router = APIRouter(prefix="/api/reports")

STREET_KINDS = set(REPORT_EFFECTS)  # broken_light, dark, deserted, felt_unsafe, well_lit
PLACE_KINDS = {"place_closed", "place_open"}
REPORT_RADIUS_M = 50  # a street report must be within 50 m of a mapped street
MAX_PER_DEVICE_PER_HOUR = 5  # blueprint §10 abuse limit: "a few reports per person per hour"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


class ReportIn(BaseModel):
    kind: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    device_id: str = Field(min_length=4, max_length=64)
    place_id: int | None = None
    at: str | None = None  # the walk time shown on the page, so the new score matches what the person sees


@router.post("")
def create_report(req: ReportIn, db: Session = Depends(get_db)):
    if req.kind not in STREET_KINDS | PLACE_KINDS:
        raise _err(422, "bad_kind", "Unknown report type.")
    now = utcnow()
    recent = db.scalar(select(func.count()).select_from(models.Report).where(
        models.Report.device_id == req.device_id, models.Report.created_at > now - timedelta(hours=1)))
    if recent >= MAX_PER_DEVICE_PER_HOUR:
        raise _err(429, "too_many", f"You can send {MAX_PER_DEVICE_PER_HOUR} reports per hour. Thank you for helping.")

    street, place = None, None
    if req.kind in PLACE_KINDS:
        place = db.get(models.Place, req.place_id) if req.place_id else None
        if not place:
            raise _err(422, "no_place", "Choose the place this report is about.")
    else:
        best = None
        for s in db.scalars(select(models.Street)).all():
            d, _, _ = locate_on_line(req.lat, req.lon, s.geometry)
            if best is None or d < best[0]:
                best = (d, s)
        if best is None or best[0] > REPORT_RADIUS_M:
            raise _err(422, "not_near_street", f"Reports must be within {REPORT_RADIUS_M} m of a mapped street.")
        street = best[1]

    # One person cannot "agree" with themselves: the same report on the same street/place within an hour is ignored.
    same_target = (models.Report.street_id == street.id) if street else (models.Report.place_id == place.id)
    dup = db.scalar(select(func.count()).select_from(models.Report).where(
        models.Report.device_id == req.device_id, models.Report.kind == req.kind, same_target,
        models.Report.created_at > now - timedelta(hours=1)))
    if dup:
        raise _err(409, "duplicate", "You already sent this report here in the last hour.")

    fades = now + timedelta(minutes=REPORT_EFFECTS[req.kind][1]) if req.kind in STREET_KINDS else None
    r = models.Report(street_id=street.id if street else None, place_id=place.id if place else None, kind=req.kind,
                      lat=req.lat, lon=req.lon, device_id=req.device_id, created_at=now, fades_at=fades)
    db.add(r)
    db.commit()
    out = {"report_id": r.id, "kind": r.kind, "fades_at_utc": fades.isoformat() + "Z" if fades else None}
    if street:
        sc = score_streets(db, parse_at(req.at))[street.id]
        out.update({"street_id": street.id, "street_name": street.name or "Unnamed road", "effect_points": REPORT_EFFECTS[req.kind][0],
                    "street_score_now": sc.score, "street_colour_now": sc.colour})
    else:
        out.update({"place_id": place.id, "place_name": place.name})
    return out


@router.get("")
def list_reports(street_id: int | None = Query(None), place_id: int | None = Query(None), db: Session = Depends(get_db)):
    """Active (not yet faded) reports for a street or place. Device ids are never returned."""
    now = utcnow()
    q = select(models.Report).order_by(models.Report.created_at.desc())
    if street_id is not None:
        q = q.where(models.Report.street_id == street_id)
    if place_id is not None:
        q = q.where(models.Report.place_id == place_id)
    out = []
    for r in db.scalars(q.limit(100)).all():
        if r.fades_at and r.fades_at < now:
            continue
        out.append({"id": r.id, "kind": r.kind, "street_id": r.street_id, "place_id": r.place_id,
                    "age_min": round((now - r.created_at).total_seconds() / 60),
                    "fades_in_min": round((r.fades_at - now).total_seconds() / 60) if r.fades_at else None})
    return {"reports": out}
