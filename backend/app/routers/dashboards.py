"""Police dashboard (SIMULATED — no connection to any real police system) and City dashboard (blueprint §11)."""

import csv
import hmac
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, utcnow

router = APIRouter(prefix="/api")
IST = timedelta(hours=5, minutes=30)


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _iso(t):
    return t.isoformat() + "Z" if t else None


def require_police(x_police_token: str | None = Header(None)) -> None:
    """Positions of people in an alert are only for the (simulated) control room."""
    if not config.POLICE_TOKEN:
        raise _err(503, "no_access_code", "The police dashboard is switched off: no access code is set (POLICE_TOKEN in backend/.env).")
    if not x_police_token:
        raise _err(401, "access_code_required", "Enter the police dashboard access code.")
    if not hmac.compare_digest(x_police_token.encode(), config.POLICE_TOKEN.encode()):
        raise _err(403, "access_code_wrong", "That access code is not correct.")


POLICE = [Depends(require_police)]


def police_alert_out(a: models.Alert, walk: models.Walk, db: Session) -> dict:
    open_ = a.status != "resolved"
    walk_live = walk.status in ("active", "checking", "alert")
    return {
        "id": a.id,
        "walk_id": walk.id,
        "walker_name": walk.walker_name,
        "walker_phone": walk.walker_phone,
        "trigger": a.trigger,
        "duress": bool(walk.duress),
        "status": a.status,
        "created_utc": _iso(a.created_at),
        "updated_utc": _iso(a.updated_at),
        "alert_position": [a.lat, a.lon] if a.lat is not None else None,
        # Live position and route only while the alert is open (blueprint §11: no tracking otherwise).
        "live_position": [walk.last_lat, walk.last_lon] if open_ and walk_live else None,
        "live_position_utc": _iso(walk.last_position_at) if open_ and walk_live else None,
        "last_moved": [walk.last_moved_lat, walk.last_moved_lon] if open_ and walk.last_moved_lat is not None else None,
        "last_moved_utc": _iso(walk.last_moved_at) if open_ else None,
        "route": walk.route if open_ else None,
        "dest": [walk.dest_lat, walk.dest_lon] if open_ else None,
        "walk_status": walk.status,
        "simulated_positions": bool(walk.simulated),
        "contacts": [c.name for c in walk.contacts] if open_ else [],
        "history": a.history or [],
        "resolved_reason": a.resolved_reason,
        "latest_street_photo": None,  # photos appear after blurring (M6)
    }


@router.get("/police/alerts", dependencies=POLICE)
def police_alerts(scope: str = Query("active", pattern="^(active|history)$"), db: Session = Depends(get_db)):
    q = select(models.Alert).where(models.Alert.level == "police").order_by(models.Alert.created_at.desc())
    q = q.where(models.Alert.status != "resolved") if scope == "active" else q.limit(100)
    return {"simulated": True, "alerts": [police_alert_out(a, db.get(models.Walk, a.walk_id), db) for a in db.scalars(q).all()]}


class StatusIn(BaseModel):
    status: str = Field(pattern="^(acknowledged|unit_sent|resolved)$")


ORDER = ["new", "acknowledged", "unit_sent", "resolved"]


@router.post("/police/alerts/{alert_id}/status", dependencies=POLICE)
def police_set_status(alert_id: int, req: StatusIn, db: Session = Depends(get_db)):
    a = db.get(models.Alert, alert_id)
    if not a or a.level != "police":
        raise _err(404, "not_found", "No such police alert.")
    if ORDER.index(req.status) <= ORDER.index(a.status):
        raise _err(409, "backwards", f"The alert is already '{a.status}'.")
    now = utcnow()
    a.status, a.updated_at = req.status, now
    a.history = [*(a.history or []), {"at": _iso(now), "status": req.status, "by": "control room (simulated)"}]
    walk = db.get(models.Walk, a.walk_id)
    label = {"acknowledged": "acknowledged the alert", "unit_sent": "sent a unit", "resolved": "marked the alert resolved"}[req.status]
    walk.events = [*(walk.events or []), {"at": _iso(now), "kind": f"police_{req.status}", "text": f"Control room {label} (simulated)."}]
    if req.status == "resolved":
        a.resolved_reason = "resolved by control room"
    db.commit()
    return police_alert_out(a, walk, db)


@router.get("/police/coverage", dependencies=POLICE)
def sentinel_coverage(db: Session = Depends(get_db)):
    """Streets seen by a Sentinel in the last hour, so gaps are visible (blueprint §11)."""
    since = utcnow() - timedelta(hours=1)
    rows = db.execute(select(models.Observation.street_id, func.count(), func.max(models.Observation.captured_at))
                      .where(models.Observation.captured_at >= since, models.Observation.street_id.is_not(None))
                      .group_by(models.Observation.street_id)).all()
    total = db.scalar(select(func.count()).select_from(models.Street).where(models.Street.in_demo_area.is_(True)))
    return {"streets_seen_last_hour": len(rows), "streets_in_area": total,
            "streets": [{"street_id": sid, "photos": n, "latest_utc": _iso(t)} for sid, n, t in rows]}


# ---------------- City dashboard (public: no personal data) ----------------

def _night(t) -> str:
    """The night a moment belongs to (India time, a night runs 18:00–06:00 and is named by its evening's date)."""
    return (t + IST - timedelta(hours=6)).date().isoformat()


def repair_list(db: Session) -> list[dict]:
    now = utcnow()
    week = now - timedelta(days=7)
    streets = {s.id: s for s in db.scalars(select(models.Street)).all()}
    entries: dict[int, dict] = {}

    def entry(sid):
        s = streets[sid]
        mid = s.geometry[len(s.geometry) // 2]
        return entries.setdefault(sid, {
            "street_id": sid, "name": s.name or f"Unnamed {s.road_class} road", "road_class": s.road_class,
            "length_m": round(s.length_m), "lat": mid[0], "lon": mid[1], "osm_way_id": s.osm_way_id,
            "broken_light_reports": 0, "reporters": set(), "dark_reports": 0, "nights_dark": set(),
            "evidence": [], "latest_lit_utc": None, "latest_dark_utc": None,
        })

    for r in db.scalars(select(models.Report).where(models.Report.street_id.is_not(None), models.Report.created_at >= week,
                                                    models.Report.kind.in_(["broken_light", "dark"]))).all():
        e = entry(r.street_id)
        if r.kind == "broken_light":
            e["broken_light_reports"] += 1
            e["reporters"].add(r.device_id)
        else:
            e["dark_reports"] += 1
        e["nights_dark"].add(_night(r.created_at))
        e["latest_dark_utc"] = max(filter(None, [e["latest_dark_utc"], r.created_at]))

    for o in db.scalars(select(models.Observation).where(models.Observation.street_id.is_not(None), models.Observation.captured_at >= week,
                                                         models.Observation.analysis_status == "done")).all():
        broken = (o.streetlights_visible or 0) > (o.streetlights_working or 0)
        if o.lighting == "dark" or broken:
            e = entry(o.street_id)
            e["nights_dark"].add(_night(o.captured_at))
            e["latest_dark_utc"] = max(filter(None, [e["latest_dark_utc"], o.captured_at]))
            e["evidence"].append({"observation_id": o.id, "captured_utc": _iso(o.captured_at), "sentinel": o.sentinel_label,
                                  "lighting": o.lighting, "streetlights_visible": o.streetlights_visible,
                                  "streetlights_working": o.streetlights_working, "description": o.description,
                                  "photo_available": False})
        elif o.lighting in ("bright", "dim") and o.street_id in entries:
            e = entries[o.street_id]
            e["latest_lit_utc"] = max(filter(None, [e["latest_lit_utc"], o.captured_at]))

    uses = {u.street_id: u for u in db.scalars(select(models.RouteUse)).all()}
    out = []
    for e in entries.values():
        u = uses.get(e["street_id"])
        possibly_fixed = bool(e["latest_lit_utc"] and e["latest_dark_utc"] and e["latest_lit_utc"] > e["latest_dark_utc"])
        out.append({
            **{k: v for k, v in e.items() if k not in ("reporters", "nights_dark", "latest_lit_utc", "latest_dark_utc")},
            "independent_reporters": len(e["reporters"]),
            "nights_dark_last_7": len(e["nights_dark"]),
            "walks_through": u.walked if u else 0,
            "routes_planned_through": u.planned if u else 0,
            "status": "possibly fixed (newer photo shows light)" if possibly_fixed else "needs checking",
            "latest_dark_utc": _iso(e["latest_dark_utc"]),
            "evidence": e["evidence"][-3:],
        })
    # Most-walked first, because fixing those helps the most people (blueprint §11); then evidence strength.
    out.sort(key=lambda x: (-(x["walks_through"] + x["routes_planned_through"]), -x["nights_dark_last_7"],
                            -x["independent_reporters"], -x["broken_light_reports"]))
    for i, x in enumerate(out, start=1):
        x["rank"] = i
    return out


@router.get("/city/repairs")
def city_repairs(db: Session = Depends(get_db)):
    items = repair_list(db)
    return {"generated_utc": _iso(utcnow()), "items": items,
            "hotspots": sorted([i for i in items if i["nights_dark_last_7"] >= 1], key=lambda x: -x["nights_dark_last_7"])[:10],
            "note": "Built from community reports (last 7 days) and analysed Sentinel photos. Photos appear after face/plate blurring."}


@router.get("/city/repairs.csv")
def city_repairs_csv(db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "street", "road_class", "length_m", "lat", "lon", "openstreetmap_way", "broken_light_reports",
                "independent_reporters", "dark_reports", "nights_dark_last_7", "walks_through", "routes_planned_through",
                "status", "latest_evidence_utc", "latest_photo_note"])
    for x in repair_list(db):
        ev = x["evidence"][-1] if x["evidence"] else None
        w.writerow([x["rank"], x["name"], x["road_class"], x["length_m"], f"{x['lat']:.6f}", f"{x['lon']:.6f}",
                    f"https://www.openstreetmap.org/way/{x['osm_way_id']}", x["broken_light_reports"], x["independent_reporters"],
                    x["dark_reports"], x["nights_dark_last_7"], x["walks_through"], x["routes_planned_through"], x["status"],
                    x["latest_dark_utc"], ev["description"] if ev else ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="shadowmap_repair_list.csv"'})
