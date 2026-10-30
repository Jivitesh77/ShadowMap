"""Walk With Me rules (blueprint §9): triggers, "Are you safe?", escalation to contacts then police, PIN and duress PIN.

All decisions are made here on the server (also when the walker's phone goes quiet). Functions take `now` so tests
can drive time. Escalation: 0 none -> 1 asked -> 2 contacts alerted -> 3 police alerted.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models
from app.services.geo import haversine_m, point_to_line_m

TRIGGER_TEXT = {
    "stopped": "stopped moving",
    "off_route": "went off the planned route",
    "late": "is running late",
    "sos": "pressed SOS",
    "duress": "entered the duress PIN",
    "battery": "phone battery is low",
}


# ---------------- secrets ----------------

def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()


def pin_matches(pin: str, stored: str | None) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex(), digest)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------- timeline ----------------

def add_event(walk: models.Walk, now: datetime, kind: str, text: str) -> None:
    walk.events = [*(walk.events or []), {"at": now.isoformat() + "Z", "kind": kind, "text": text}]


def raise_alert(db: Session, walk: models.Walk, now: datetime, level: str, trigger: str) -> models.Alert:
    a = models.Alert(walk_id=walk.id, level=level, trigger=trigger, status="new", created_at=now, updated_at=now,
                     lat=walk.last_lat, lon=walk.last_lon, history=[{"at": now.isoformat() + "Z", "status": "new", "by": "system"}])
    db.add(a)
    return a


def _resolve_open_alerts(db: Session, walk: models.Walk, now: datetime, reason: str) -> None:
    for a in db.scalars(select(models.Alert).where(models.Alert.walk_id == walk.id, models.Alert.status != "resolved")).all():
        a.status, a.resolved_reason, a.updated_at = "resolved", reason, now
        a.history = [*(a.history or []), {"at": now.isoformat() + "Z", "status": "resolved", "by": reason}]


def _start_check(db: Session, walk: models.Walk, now: datetime, trigger: str) -> None:
    walk.status, walk.check_started_at, walk.check_trigger, walk.escalation = "checking", now, trigger, 1
    raise_alert(db, walk, now, "ask", trigger)
    add_event(walk, now, "check", f"{walk.walker_name} {TRIGGER_TEXT[trigger]}. ShadowMap asked “Are you safe?”")


def escalate_to_contacts(db: Session, walk: models.Walk, now: datetime, trigger: str) -> None:
    walk.status, walk.escalation, walk.contacts_alerted_at = "alert", 2, now
    raise_alert(db, walk, now, "contacts", trigger)
    add_event(walk, now, "alert_contacts", f"ALERT: {walk.walker_name} has not answered “Are you safe?” ({TRIGGER_TEXT[trigger]}). Live location below.")


def escalate_to_police(db: Session, walk: models.Walk, now: datetime, trigger: str) -> None:
    walk.status, walk.escalation = "alert", 3
    raise_alert(db, walk, now, "police", trigger)
    add_event(walk, now, "alert_police", "The police dashboard has been alerted (simulated — no real police connection).")


# ---------------- inputs from the walker ----------------

def update_position(db: Session, walk: models.Walk, now: datetime, lat: float, lon: float, battery_pct: int | None = None) -> None:
    walk.last_lat, walk.last_lon, walk.last_position_at = lat, lon, now
    if walk.last_moved_lat is None or haversine_m(lat, lon, walk.last_moved_lat, walk.last_moved_lon) >= config.WALK_MOVE_M:
        walk.last_moved_lat, walk.last_moved_lon, walk.last_moved_at = lat, lon, now
    off = point_to_line_m(lat, lon, walk.route) > config.WALK_TIMERS["off_route_m"] if walk.route else False
    walk.off_route_since = (walk.off_route_since or now) if off else None
    if battery_pct is not None:
        was_low = walk.battery_pct is not None and walk.battery_pct < config.WALK_BATTERY_LOW
        walk.battery_pct = battery_pct
        if battery_pct < config.WALK_BATTERY_LOW and not was_low:
            raise_alert(db, walk, now, "info", "battery")
            add_event(walk, now, "battery", f"{walk.walker_name}'s phone battery is at {battery_pct}%. (Not an alarm.)")
    if haversine_m(lat, lon, walk.dest_lat, walk.dest_lon) <= config.WALK_ARRIVE_M and walk.status in ("active",):
        walk.status, walk.ended_at = "arrived", now
        add_event(walk, now, "arrived", f"{walk.walker_name} reached safely at {(now + timedelta(hours=5, minutes=30)).strftime('%I:%M %p').lstrip('0')}. Location sharing stopped.")


def answer_check(db: Session, walk: models.Walk, now: datetime, pin: str) -> str:
    """'safe' (real PIN), 'duress' (duress PIN: looks the same to the walker), or 'wrong'."""
    if pin_matches(pin, walk.duress_pin_hash):
        walk.duress = True
        if walk.escalation < 2:
            escalate_to_contacts(db, walk, now, "duress")
        if walk.escalation < 3:
            escalate_to_police(db, walk, now, "duress")
        add_event(walk, now, "duress", f"{walk.walker_name} entered the DURESS PIN: she may be forced to cancel. Treat as an emergency.")
        return "duress"
    if pin_matches(pin, walk.pin_hash):
        if walk.duress:
            return "safe"  # cannot undo a duress alert from the walker's phone
        was = walk.escalation or 0
        _resolve_open_alerts(db, walk, now, "walker confirmed safe with PIN")
        walk.status, walk.check_started_at, walk.check_trigger, walk.escalation = "active", None, None, 0
        walk.contacts_alerted_at = None
        walk.last_moved_at = now  # restart the stop timer
        walk.off_route_since = None
        if walk.expected_arrival_at and now > walk.expected_arrival_at:
            walk.expected_arrival_at = now  # "running late" is asked again only after another full late period
        if was:
            add_event(walk, now, "safe", f"{walk.walker_name} confirmed “I'm safe” with her PIN." + (" False alarm." if was >= 2 else ""))
        return "safe"
    return "wrong"


def sos(db: Session, walk: models.Walk, now: datetime) -> None:
    """SOS skips straight to the police (and tells contacts)."""
    if walk.escalation < 2:
        escalate_to_contacts(db, walk, now, "sos")
    escalate_to_police(db, walk, now, "sos")
    add_event(walk, now, "sos", f"{walk.walker_name} pressed SOS.")


def end_walk(db: Session, walk: models.Walk, now: datetime, pin: str) -> str:
    """Ending needs the PIN too (someone grabbing the phone must not be able to stop the walk). Duress PIN escalates."""
    result = answer_check(db, walk, now, pin)
    if result == "safe" and not walk.duress:
        walk.status, walk.ended_at = "ended", now
        add_event(walk, now, "ended", f"{walk.walker_name} ended the walk. Location sharing stopped.")
    return result


# ---------------- the clock ----------------

def evaluate(db: Session, walk: models.Walk, now: datetime) -> None:
    """Apply the time-based rules to one walk."""
    t = config.WALK_TIMERS
    if walk.status == "active":
        near_dest = walk.last_lat is not None and haversine_m(walk.last_lat, walk.last_lon, walk.dest_lat, walk.dest_lon) <= config.WALK_ARRIVE_M * 2
        # Off the route is checked first: when someone is both off the route and still, that is the more useful reason.
        if walk.off_route_since and (now - walk.off_route_since).total_seconds() >= t["off_route_s"]:
            _start_check(db, walk, now, "off_route")
        elif walk.last_moved_at and (now - walk.last_moved_at).total_seconds() >= t["stop_s"] and not near_dest:
            _start_check(db, walk, now, "stopped")
        elif walk.expected_arrival_at and (now - walk.expected_arrival_at).total_seconds() >= t["late_s"]:
            _start_check(db, walk, now, "late")
    elif walk.status == "checking" and walk.escalation == 1:
        if (now - walk.check_started_at).total_seconds() >= t["ask_s"]:
            escalate_to_contacts(db, walk, now, walk.check_trigger)
    elif walk.status == "alert" and walk.escalation == 2 and walk.contacts_alerted_at:
        if (now - walk.contacts_alerted_at).total_seconds() >= t["contacts_to_police_s"]:
            escalate_to_police(db, walk, now, walk.check_trigger or "no_answer")


def evaluate_all(db: Session, now: datetime) -> None:
    for walk in db.scalars(select(models.Walk).where(models.Walk.status.in_(["active", "checking", "alert"]))).all():
        evaluate(db, walk, now)
    db.commit()
