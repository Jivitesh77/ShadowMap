"""Walk With Me rules (blueprint §9): triggers, "Are you safe?", escalation to contacts then police, PIN and duress PIN.

All decisions are made here on the server (also when the walker's phone goes quiet). Functions take `now` so tests
can drive time. Escalation: 0 none -> 1 asked -> 2 contacts alerted -> 3 police alerted.

Concurrency: the background clock and the walker's requests change the same walk. Every walk row carries a version
number (models.Walk.version); a write made from an older copy is refused by the database. `save` then rolls back
(also dropping any alert rows that change created), re-reads the newest walk and applies the change again.
"""

import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app import config, models
from app.logging_setup import walk_ref
from app.services.geo import haversine_m, point_to_line_m

log = logging.getLogger("shadowmap.walks")
RUNNING = ("active", "checking", "alert")
FINISHED = ("arrived", "ended", "expired")  # terminal: never shared or monitored again
SAVE_ATTEMPTS = 5
R = TypeVar("R")

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


# ---------------- safe writes ----------------

class WalkConflict(Exception):
    """The walk kept changing under us; nothing was written. Carries only walk_ref(), never the walk id."""


def save(db: Session, walk: models.Walk, change: Callable[[], R], attempts: int = SAVE_ATTEMPTS) -> R:
    """Apply `change` (which reads and modifies `walk`) and commit. If another writer committed a newer version of the
    walk first, roll back and apply `change` again to the newest state; a stale copy is never written over newer data."""
    ref = walk_ref(walk.id)  # logs never contain the walk id itself (it is the trip link's secret)
    for attempt in range(1, attempts + 1):
        try:
            result = change()  # may already write: a query inside it flushes pending changes first (autoflush)
            db.commit()
            return result
        except StaleDataError:
            db.rollback()  # discards this attempt's changes and new alert rows, and expires `walk` so it is re-read
            if attempt < attempts:
                log.info("%s changed meanwhile; re-applying the change to the newest state (attempt %d of %d)", ref, attempt + 1, attempts)
    log.warning("%s still changing after %d attempts; nothing was written", ref, attempts)
    raise WalkConflict(ref)


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

def update_position(db: Session, walk: models.Walk, now: datetime, lat: float, lon: float, battery_pct: int | None = None,
                    accuracy_m: float | None = None) -> None:
    walk.last_lat, walk.last_lon, walk.last_position_at, walk.last_accuracy_m = lat, lon, now, accuracy_m
    if accuracy_m is None or accuracy_m <= config.WALK_MAX_ACCURACY_M:
        # Only reasonably accurate fixes move the safety clocks: a poor fix must neither fake "moving"
        # (GPS drift) nor fake "off route". Movement must also exceed the fix's own uncertainty.
        need = max(config.WALK_MOVE_M, accuracy_m or 0)
        if walk.last_moved_lat is None or haversine_m(lat, lon, walk.last_moved_lat, walk.last_moved_lon) >= need:
            walk.last_moved_lat, walk.last_moved_lon, walk.last_moved_at = lat, lon, now
        off = point_to_line_m(lat, lon, walk.route) > config.WALK_TIMERS["off_route_m"] if walk.route else False
        walk.off_route_since = (walk.off_route_since or now) if off else None  # one stray fix back on route resets it
    if battery_pct is not None:
        was_low = walk.battery_pct is not None and walk.battery_pct < config.WALK_BATTERY_LOW
        walk.battery_pct = battery_pct
        if battery_pct < config.WALK_BATTERY_LOW and not was_low:
            raise_alert(db, walk, now, "info", "battery")
            add_event(walk, now, "battery", f"{walk.walker_name}'s phone battery is at {battery_pct}%. (Not an alarm.)")
    accurate = accuracy_m is None or accuracy_m <= config.WALK_MAX_ACCURACY_M
    at_destination = accurate and haversine_m(lat, lon, walk.dest_lat, walk.dest_lon) <= config.WALK_ARRIVE_M
    if at_destination and walk.status in ("active",):
        walk.status, walk.ended_at = "arrived", now
        # Only the phone's position is known: never claim the walker is safe.
        add_event(walk, now, "arrived", f"{walk.walker_name}'s phone reached the destination at {(now + timedelta(hours=5, minutes=30)).strftime('%I:%M %p').lstrip('0')}. The walk ended and location sharing stopped.")
    elif at_destination and walk.status in ("checking", "alert") and not _arrival_already_noted(walk):
        # Agreed 2026-10-31: while "Are you safe?" is unanswered (or an SOS / duress alert is open), reaching the
        # destination is only recorded for contacts and police. The phone may not be in the walker's hands, so it never
        # counts as an answer: the question, the escalation clock, alerts and location sharing all continue.
        add_event(walk, now, ARRIVAL_UNCONFIRMED,
                  f"{walk.walker_name}'s phone reached the destination area at {(now + timedelta(hours=5, minutes=30)).strftime('%I:%M %p').lstrip('0')}, "
                  "but “Are you safe?” has not been answered. This does not mean the walker is safe: the alert continues "
                  "until the walker answers with the PIN.")


ARRIVAL_UNCONFIRMED = "arrival_unconfirmed"
# Timeline entries that start (or end) a safety episode. One arrival note per episode: repeated GPS fixes add nothing.
_EPISODE_EVENTS = {"check", "sos", "duress", "safe"}


def _arrival_already_noted(walk: models.Walk) -> bool:
    for e in reversed(walk.events or []):
        if e.get("kind") == ARRIVAL_UNCONFIRMED:
            return True
        if e.get("kind") in _EPISODE_EVENTS:
            return False
    return False


def emergency_after_end(db: Session, walk: models.Walk, now: datetime, trigger: str) -> None:
    """SOS or duress PIN from the walker's phone after the walk finished: the police dashboard is still alerted, but the
    walk stays finished (no sharing, no GPS monitoring, no escalation clock). Repeats never add a second open alert."""
    label = {"sos": "pressed SOS", "duress": "entered the DURESS PIN"}[trigger]
    if trigger == "duress":
        walk.duress = True
    if _open_police_alert(db, walk):
        add_event(walk, now, f"{trigger}_after_end", f"{walk.walker_name} {label} again after the walk had ended.")
        return
    raise_alert(db, walk, now, "police", f"{trigger}_after_end")
    add_event(walk, now, f"{trigger}_after_end",
              f"EMERGENCY: {walk.walker_name} {label} AFTER the walk had {walk.status}. The police dashboard was alerted "
              "(simulated). Location sharing stays off: the last known position is from before the end.")


def answer_check(db: Session, walk: models.Walk, now: datetime, pin: str) -> str:
    """'safe' (real PIN), 'duress' (duress PIN: looks the same to the walker), 'wrong', 'locked', or 'finished'.
    After WALK_PIN_MAX_FAILURES wrong PINs the phone is locked out for WALK_PIN_LOCK_S and contacts are told.
    A finished walk is never restarted: every PIN gets 'finished'; the duress PIN still alerts the police silently."""
    if walk.status in FINISHED:
        if pin_matches(pin, walk.duress_pin_hash):
            emergency_after_end(db, walk, now, "duress")
        return "finished"
    if walk.pin_locked_until and now < walk.pin_locked_until:
        return "locked"
    result = _check_pin(db, walk, now, pin)
    if result == "wrong":
        walk.pin_failures = (walk.pin_failures or 0) + 1
        if walk.pin_failures >= config.WALK_PIN_MAX_FAILURES:
            walk.pin_locked_until, walk.pin_failures = now + timedelta(seconds=config.WALK_PIN_LOCK_S), 0
            add_event(walk, now, "pin_failures", f"A wrong PIN was entered {config.WALK_PIN_MAX_FAILURES} times on {walk.walker_name}'s phone.")
    else:
        walk.pin_failures = 0
    return result


def _check_pin(db: Session, walk: models.Walk, now: datetime, pin: str) -> str:
    if pin_matches(pin, walk.duress_pin_hash):
        walk.duress = True
        if walk.escalation < 2:
            escalate_to_contacts(db, walk, now, "duress")
        if walk.escalation < 3 or not _open_police_alert(db, walk):
            escalate_to_police(db, walk, now, "duress")
        add_event(walk, now, "duress", f"{walk.walker_name} entered the DURESS PIN: the walker may be forced to cancel. Treat as an emergency.")
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
            add_event(walk, now, "safe", f"{walk.walker_name} confirmed “I'm safe” with the walker's PIN." + (" False alarm." if was >= 2 else ""))
        return "safe"
    return "wrong"


def _open_police_alert(db: Session, walk: models.Walk) -> bool:
    return db.scalar(select(models.Alert.id).where(models.Alert.walk_id == walk.id, models.Alert.level == "police",
                                                   models.Alert.status != "resolved").limit(1)) is not None


def sos(db: Session, walk: models.Walk, now: datetime) -> None:
    """SOS skips straight to the police (and tells contacts). Pressing it again never creates a duplicate alert.
    After the walk finished, the police are still alerted but the walk stays finished (emergency_after_end)."""
    if walk.status in FINISHED:
        emergency_after_end(db, walk, now, "sos")
        return
    walk.check_trigger = "sos"
    if _open_police_alert(db, walk):
        add_event(walk, now, "sos", f"{walk.walker_name} pressed SOS again.")
        return
    if walk.escalation < 2:
        escalate_to_contacts(db, walk, now, "sos")
    escalate_to_police(db, walk, now, "sos")
    add_event(walk, now, "sos", f"{walk.walker_name} pressed SOS.")


def end_walk(db: Session, walk: models.Walk, now: datetime, pin: str, revoke: bool = False) -> str:
    """Ending needs the PIN too (someone grabbing the phone must not be able to stop the walk). Duress PIN escalates.
    Location sharing stops at once; with revoke=True the contact link stops working at once as well."""
    result = answer_check(db, walk, now, pin)
    if result == "safe" and not walk.duress:
        walk.status, walk.ended_at = "ended", now
        if revoke:
            walk.revoked_at = now
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


def tick(db: Session, walk: models.Walk, now: datetime) -> None:
    """One clock step for one walk (re-checked on the newest state by `save`)."""
    if walk.status not in RUNNING:
        return
    if walk.started_at and now - walk.started_at > timedelta(hours=config.WALK_MAX_HOURS):
        walk.status, walk.ended_at = "expired", now  # never shared forever; deleted 24 h later by retention
        add_event(walk, now, "expired", "This walk ran for too long and was closed automatically. Location sharing stopped.")
        return
    evaluate(db, walk, now)


def evaluate_all(db: Session, now: datetime) -> None:
    """The clock: each running walk in its own short transaction, so one busy walk never holds up or overwrites others."""
    for walk_id in db.scalars(select(models.Walk.id).where(models.Walk.status.in_(RUNNING))).all():
        walk = db.get(models.Walk, walk_id)
        if walk is None:
            continue
        try:
            save(db, walk, lambda: tick(db, walk, now))
        except WalkConflict:
            log.warning("%s kept changing; the walk clock tries again next round", walk_ref(walk_id))
