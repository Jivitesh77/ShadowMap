"""Walk With Me endpoints (blueprint §9): walker, trusted contacts, "Where am I" card."""

import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, utcnow
from app.rate_limit import rate_limit
from app.routers.map import parse_at
from app.routers.route import Point, RouteRequest, plan_routes, save_route_use, suggested_street_ids
from app.services import walks as W
from app.services.geo import haversine_m, locate_on_line
from app.services import cities
from app.services.street_state import places_at

router = APIRouter(prefix="/api")

# Real numbers from the Government of India helpline directory (blueprint §9). In DEMO_MODE they are never dialled:
# every call button rings DEMO_CALL_NUMBER instead.
HELPLINES = {"emergency": "112", "women": "181", "police": "100"}


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _iso(t):
    return t.isoformat() + "Z" if t else None


def get_walk(db: Session, walk_id: str) -> models.Walk:
    walk = db.get(models.Walk, walk_id)
    if not walk:
        raise _err(404, "not_found", "This walk does not exist or has expired.")
    return walk


def walker_walk(walk_id: str, x_walk_token: str | None = Header(None), db: Session = Depends(get_db)) -> models.Walk:
    """Only the walker's own phone (which received the private walk token) may control the walk."""
    walk = get_walk(db, walk_id)
    if not x_walk_token or not walk.walker_token_hash or not secrets.compare_digest(W.hash_token(x_walk_token), walk.walker_token_hash):
        raise _err(403, "not_walker", "Only the walker's phone can do this.")
    return walk


@router.get("/walks/config")
def walk_config():
    return {
        "demo_mode": config.DEMO_MODE,
        "timers": config.WALK_TIMERS,
        "helplines": HELPLINES,
        # In demo mode every call button rings this team number; empty = buttons say so and dial nothing.
        "demo_call_number": config.DEMO_CALL_NUMBER if config.DEMO_MODE else None,
    }


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(None, max_length=20)

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v):
        if v and not re.fullmatch(r"\+?[0-9 ]{6,20}", v):
            raise ValueError("phone numbers may contain digits, spaces and a leading +")
        return v or None


class StartWalk(BaseModel):
    walker_name: str = Field(min_length=1, max_length=80)
    walker_phone: str | None = Field(None, max_length=20)
    contacts: list[ContactIn] = Field(min_length=1, max_length=config.WALK_MAX_CONTACTS)
    pin: str = Field(pattern=r"^\d{4}$")
    duress_pin: str | None = Field(None, pattern=r"^\d{4}$")
    start: Point
    end: Point
    simulated: bool = False  # demo only: positions are simulated along the route
    city: str | None = None


@router.post("/walks", dependencies=[Depends(rate_limit("walk_start"))])  # only starting; SOS, PIN, positions are never limited
def start_walk(req: StartWalk, db: Session = Depends(get_db)):
    if req.duress_pin and req.duress_pin == req.pin:
        raise _err(422, "same_pins", "The duress PIN must be different from your PIN.")
    if req.simulated and not config.DEMO_MODE:
        raise _err(422, "no_simulation", "Simulated walks are only allowed in demo mode.")
    r = plan_routes(RouteRequest(start=req.start, end=req.end, city=req.city), db)  # the server plans the route itself
    safest = r["safest"]
    now = utcnow()
    token = secrets.token_urlsafe(24)
    walk = models.Walk(
        id=secrets.token_urlsafe(12), city=r["city"], walker_name=req.walker_name, walker_phone=req.walker_phone,
        route=safest["geometry"], route_length_m=safest["distance_m"], dest_lat=req.end.lat, dest_lon=req.end.lon,
        start_lat=req.start.lat, start_lon=req.start.lon, pin_hash=W.hash_pin(req.pin),
        duress_pin_hash=W.hash_pin(req.duress_pin) if req.duress_pin else None, status="active", started_at=now,
        expected_arrival_at=now + timedelta(minutes=safest["duration_min"]), last_lat=req.start.lat, last_lon=req.start.lon,
        last_position_at=now, last_moved_at=now, last_moved_lat=req.start.lat, last_moved_lon=req.start.lon,
        walker_token_hash=W.hash_token(token), escalation=0, duress=False, simulated=req.simulated, events=[],
    )
    for c in req.contacts:
        walk.contacts.append(models.Contact(name=c.name, phone=c.phone))
    W.add_event(walk, now, "started", f"{req.walker_name} started a {safest['distance_m']} m walk (about {safest['duration_min']} min)."
                + (" Positions are simulated for the demo." if req.simulated else ""))
    db.add(walk)
    db.commit()  # the walk is saved first: the repair-ranking counter can never cost a walk
    save_route_use(db, suggested_street_ids(r), "walked")
    return {"walk_id": walk.id, "walker_token": token, "contact_path": f"/trip/{walk.id}",
            "expected_arrival_utc": _iso(walk.expected_arrival_at), "route": walk.route, "timers": config.WALK_TIMERS}


def walker_view(walk: models.Walk) -> dict:
    """What the walker's own screen shows. A duress alert is never revealed here."""
    asking = walk.status == "checking" or (walk.status == "alert" and not walk.duress)
    shown = "active" if walk.duress and walk.status == "alert" else walk.status
    return {"walk_id": walk.id, "status": shown, "asking": asking, "trigger": walk.check_trigger if asking else None,
            "check_started_utc": _iso(walk.check_started_at) if asking else None, "escalation": 0 if walk.duress else walk.escalation,
            "expected_arrival_utc": _iso(walk.expected_arrival_at), "route": walk.route, "dest": [walk.dest_lat, walk.dest_lon],
            "last": [walk.last_lat, walk.last_lon], "contacts": [{"name": c.name, "phone": c.phone} for c in walk.contacts],
            "simulated": walk.simulated, "timers": config.WALK_TIMERS,
            "last_position_utc": _iso(walk.last_position_at), "last_accuracy_m": walk.last_accuracy_m,
            "sharing": walk.status in ("active", "checking", "alert"),
            "pin_locked_until_utc": _iso(walk.pin_locked_until)}


@router.get("/walks/{walk_id}/state")
def walk_state(walk: models.Walk = Depends(walker_walk)):
    return walker_view(walk)


class Position(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    battery_pct: int | None = Field(None, ge=0, le=100)
    accuracy_m: float | None = Field(None, ge=0, le=100000)


def _save(db: Session, walk: models.Walk, change):
    """Version-checked write with retries on the newest state (services/walks.save)."""
    try:
        return W.save(db, walk, change)
    except W.WalkConflict:
        raise _err(503, "busy", "The walk was being updated at the same moment. Please try again.")


@router.post("/walks/{walk_id}/position")
def walk_position(req: Position, walk: models.Walk = Depends(walker_walk), db: Session = Depends(get_db)):
    now = utcnow()

    def change():
        if walk.status in W.FINISHED:
            return  # sharing has stopped: positions are no longer accepted
        W.update_position(db, walk, now, req.lat, req.lon, req.battery_pct, req.accuracy_m)
        W.evaluate(db, walk, now)

    _save(db, walk, change)
    return walker_view(walk)


class PinIn(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")


class EndIn(PinIn):
    revoke: bool = False  # also switch the contact link off immediately


def _pin_error(result: str) -> None:
    if result == "finished":  # same answer for every PIN, so the duress PIN stays invisible here too
        raise _err(409, "walk_finished", "This walk has already finished. Location sharing stays off.")
    if result == "locked":
        raise _err(429, "pin_locked", f"Too many wrong PINs. Wait {config.WALK_PIN_LOCK_S} seconds and try again.")
    if result == "wrong":
        raise _err(403, "wrong_pin", "That PIN is not correct.")


@router.post("/walks/{walk_id}/safe")
def walk_safe(req: PinIn, walk: models.Walk = Depends(walker_walk), db: Session = Depends(get_db)):
    now = utcnow()
    result = _save(db, walk, lambda: W.answer_check(db, walk, now, req.pin))
    _pin_error(result)
    return {"ok": True, **walker_view(walk)}  # same answer for the real and the duress PIN


@router.post("/walks/{walk_id}/sos")
def walk_sos(walk: models.Walk = Depends(walker_walk), db: Session = Depends(get_db)):
    now = utcnow()
    _save(db, walk, lambda: W.sos(db, walk, now))  # after the end: police alerted, walk stays finished
    return {"ok": True}


@router.post("/walks/{walk_id}/end")
def walk_end(req: EndIn, walk: models.Walk = Depends(walker_walk), db: Session = Depends(get_db)):
    now = utcnow()
    result = _save(db, walk, lambda: W.end_walk(db, walk, now, req.pin, req.revoke))
    _pin_error(result)
    return {"ok": True, "status": "ended"}  # same answer for the duress PIN


class Note(BaseModel):
    kind: str = Field(pattern="^calling$")
    target: str = Field(pattern="^(112|181|police|contact|fake)$")


@router.post("/walks/{walk_id}/note")
def walk_note(req: Note, walk: models.Walk = Depends(walker_walk), db: Session = Depends(get_db)):
    """Tell contacts the walker is calling for help, so someone knows if the call drops (blueprint §9)."""
    if req.target != "fake":
        label = {"112": "112 (emergency)", "181": "181 (Women Helpline)", "police": "the nearest police station", "contact": "a trusted contact"}[req.target]
        now = utcnow()
        text = f"{walk.walker_name} is calling {label}." + (" (Demo: a team phone rings instead.)" if config.DEMO_MODE else "")
        _save(db, walk, lambda: W.add_event(walk, now, "calling", text))
    return {"ok": True}


@router.get("/walks/{walk_id}/contact")
def contact_view(walk_id: str, db: Session = Depends(get_db)):
    """The trusted contact's live trip page. Location, route and timeline only while the walk is running.
    No phone numbers (anyone holding the link could see them). Revoked links stop at once; ended ones after
    WALK_LINK_FINAL_HOURS, showing only the final status meanwhile."""
    walk = get_walk(db, walk_id)
    if walk.revoked_at:
        raise _err(410, "revoked", "The walker has switched this trip link off.")
    live = walk.status in ("active", "checking", "alert")
    if not live and walk.ended_at and utcnow() - walk.ended_at > timedelta(hours=config.WALK_LINK_FINAL_HOURS):
        raise _err(410, "expired", "This trip link has expired because the walk ended.")
    base = {
        "walker_name": walk.walker_name,
        "status": walk.status,
        "started_utc": _iso(walk.started_at),
        "expected_arrival_utc": _iso(walk.expected_arrival_at),
        "ended_utc": _iso(walk.ended_at),
        "simulated": walk.simulated,
    }
    if not live:  # final status only: the outcome, nothing about where the walker went
        final = next((e for e in reversed(walk.events or []) if e["kind"] in ("arrived", "ended", "expired")), None)
        # An SOS / duress PIN after the end is shown too (contacts must know), still without any position.
        after = [e for e in walk.events or [] if e["kind"] in ("sos_after_end", "duress_after_end")]
        return {**base, "duress": bool(walk.duress), "escalation": walk.escalation, "trigger": None, "route": None,
                "dest": None, "last": None, "last_position_utc": None, "battery_pct": None,
                "events": ([final] if final else []) + after, "alerts": []}
    alerts = db.scalars(select(models.Alert).where(models.Alert.walk_id == walk.id, models.Alert.level.in_(["contacts", "police", "info"]))
                        .order_by(models.Alert.created_at)).all()
    return {
        **base,
        "duress": bool(walk.duress),
        "escalation": walk.escalation,
        "trigger": walk.check_trigger,
        "route": walk.route,
        "dest": [walk.dest_lat, walk.dest_lon],
        "last": [walk.last_lat, walk.last_lon],
        "last_position_utc": _iso(walk.last_position_at),
        "last_accuracy_m": walk.last_accuracy_m,
        "battery_pct": walk.battery_pct,
        "events": walk.events or [],
        "alerts": [{"level": a.level, "trigger": a.trigger, "status": a.status, "created_utc": _iso(a.created_at)} for a in alerts],
    }


class WhereIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    at: str | None = None
    city: str | None = None


@router.post("/where-am-i")
def where_am_i(req: WhereIn, db: Session = Depends(get_db)):
    """Words to tell a helpline operator: street, nearest landmark, nearest open help point, nearest police (blueprint §9)."""
    at = parse_at(req.at)
    city = cities.resolve(req.city)
    best = None
    for s in db.scalars(select(models.Street).where(models.Street.city == city)).all():
        d, _, _ = locate_on_line(req.lat, req.lon, s.geometry)
        if best is None or d < best[0]:
            best = (d, s)
    street = None
    if best and best[0] <= 100:
        s = best[1]
        street = s.name or {"main": "an unnamed main road", "residential": "an unnamed residential street"}.get(s.road_class, "an unnamed lane")
    places = places_at(db, at, city)

    def nearest(pred):
        cands = [(haversine_m(req.lat, req.lon, pa.place.lat, pa.place.lon), pa) for pa in places if pred(pa)]
        if not cands:
            return None
        d, pa = min(cands, key=lambda x: x[0])
        return {"name": pa.place.name, "category": pa.place.category, "status": pa.status, "distance_m": round(d),
                "phone": pa.place.phone, "lat": pa.place.lat, "lon": pa.place.lon}

    return {
        "lat": req.lat, "lon": req.lon,
        "street": street,
        "landmark": nearest(lambda pa: bool(pa.place.name)),
        "nearest_open": nearest(lambda pa: pa.status == "open"),
        "nearest_police": nearest(lambda pa: pa.place.category == "police"),
    }
