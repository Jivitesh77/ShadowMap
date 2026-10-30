"""Background worker for Sentinel photos (M6): redact → analyse → approve, then delete the original.

Order matters for privacy:
1. Faces and plates are blurred locally (redaction.py). If that fails, nothing is sent to Gemini and nothing is shown.
2. Only the BLURRED copy is sent to Gemini (photo_analysis.py) for the street analysis and a privacy double-check.
3. The blurred copy becomes public only if Gemini reports no recognisable face and no readable plate left.
4. The original is deleted as soon as it is no longer needed (otherwise by retention.py at photo_delete_at).
Pending, failed, unclear or expired observations never affect safety scores (only analysis_status == "done" counts).
State lives in the database, so the worker simply continues after a restart.
"""

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select

from app import config, models
from app.db import SessionLocal, utcnow
from app.services import photo_analysis, redaction
from app.services.scoring import PhotoFields, photo_score

log = logging.getLogger("shadowmap.photos")


def _delete_original(o: models.Observation) -> None:
    if o.photo_path:
        p = Path(o.photo_path)
        if p.resolve().parent == config.PHOTO_DIR.resolve():
            p.unlink(missing_ok=True)
    o.photo_path = None


def redact_step(o: models.Observation, redact_fn=None) -> bool:
    """Blur faces/plates into REDACTED_DIR. Returns True on success; on any failure the photo stays private."""
    dest = config.REDACTED_DIR / f"obs{o.id}.jpg"
    try:
        r = (redact_fn or redaction.redact_file)(Path(o.photo_path), dest)
    except Exception as err:  # any failure at all: keep private, never analyse, never score
        dest.unlink(missing_ok=True)
        o.redaction_status, o.photo_public, o.redacted_path = "failed", False, None
        o.privacy_note = f"Blurring failed ({str(err)[:120]}); photo kept private and not analysed."
        o.analysis_status = "blocked"  # never send an unblurred photo to the AI; never scored
        return False
    o.redaction_status, o.redacted_path = "done", str(dest)
    o.faces_blurred, o.plates_blurred = r.faces, r.plates
    return True


def record_failure(o: models.Observation, now: datetime, kind: str, message: str) -> str:
    """Count one failed attempt (every kind of error counts). After ANALYSIS_MAX_ATTEMPTS the photo is 'failed':
    private, never scored, original deleted. Network-type errors back off 1, 2, 4… min (max 15); others retry in 10 s."""
    o.analysis_attempts = (o.analysis_attempts or 0) + 1
    o.analysis_error = f"{kind}: {message}"[:300]
    o.photo_public = False
    if o.analysis_attempts >= config.ANALYSIS_MAX_ATTEMPTS:
        o.analysis_status, o.next_attempt_at = "failed", None
        return "failed"
    backoff = 60 * 2 ** (o.analysis_attempts - 1) if kind in ("rate_limited", "timeout", "http") else 10
    o.next_attempt_at = now + timedelta(seconds=min(backoff, 900))
    return "retry"


def approval(o: models.Observation, a) -> tuple[bool, list[str]]:
    """Conservative prototype rule: public only if every check passes. Gemini's judgement is NOT treated as proof that
    an undetected face or plate is safe: if the AI reports people/vehicles but our detector blurred none, the photo
    stays private. This does not make Indian number-plate detection reliable — it keeps doubtful photos private."""
    reasons = []
    if o.redaction_status != "done":
        reasons.append("blurring did not complete")
    if a.unclear:
        reasons.append("photo unclear")
    if a.confidence not in ("medium", "high"):
        reasons.append("analysis uncertain")
    if a.unredacted_faces or a.legible_plates:
        reasons.append(f"AI still saw {a.unredacted_faces} face(s) / {a.legible_plates} readable plate(s) after blurring")
    if a.vehicles in ("some", "busy") and not (o.plates_blurred or 0):
        reasons.append("vehicles reported but no number plate was detected and blurred")
    if a.people in ("few", "many") and not (o.faces_blurred or 0):
        reasons.append("people reported but no face was detected and blurred")
    if a.vehicles is None or a.people is None:
        reasons.append("analysis incomplete")
    return (not reasons), reasons


def analyse_step(o: models.Observation, now: datetime, analyse_fn=None) -> str:
    """Returns 'done', 'unclear', 'retry', 'failed', 'expired' or 'waiting' (no key)."""
    try:
        data = Path(o.redacted_path).read_bytes()
    except (OSError, TypeError):  # the blurred copy is gone (e.g. deleted at the 6-hour limit or with its video)
        o.photo_public, o.analysis_error = False, "blurred copy missing"
        o.analysis_status = "expired" if o.photo_delete_at and o.photo_delete_at <= now else "failed"
        return o.analysis_status
    try:
        a = (analyse_fn or photo_analysis.analyse)(data)
    except photo_analysis.AnalysisError as err:
        if err.kind == "no_key":
            return "waiting"
        return record_failure(o, now, err.kind, err.message)
    except Exception as err:  # anything unexpected still counts as an attempt
        return record_failure(o, now, "unexpected", type(err).__name__)
    o.analysis_error, o.next_attempt_at = None, None
    public, reasons = approval(o, a)
    o.photo_public = public
    o.privacy_note = None if public else ("Kept private: " + "; ".join(reasons) + ".")[:200]
    if a.unclear:
        o.analysis_status = "unclear"  # blueprint §6: ignored, not scored
        return "unclear"
    o.lighting, o.people, o.vehicles, o.isolation = a.lighting, a.people, a.vehicles, a.isolation
    o.streetlights_visible, o.streetlights_working = a.streetlights_visible, a.streetlights_working
    o.open_places_count, o.open_places_types, o.hazards = a.open_places_count, a.open_places_types, a.hazards
    o.description, o.confidence, o.uncertainty = a.description, a.confidence, a.uncertainty
    o.photo_score = photo_score(PhotoFields(a.lighting, a.people, a.open_places_count, a.vehicles, a.isolation, a.hazards))
    o.analysis_status = "done"
    return "done"


def process(o: models.Observation, now: datetime, redact_fn=None, analyse_fn=None) -> str:
    """One step of work for one observation."""
    if not o.photo_path and o.redaction_status != "done":
        if o.analysis_status == "pending":
            o.analysis_status = "expired"  # original deleted before it could be processed
        return "expired"
    if o.redaction_status in (None, "pending"):
        if not redact_step(o, redact_fn):
            return "blocked"
    if o.analysis_status != "pending":
        return o.analysis_status
    if analyse_fn is None and not config.GEMINI_API_KEY:
        return "waiting"  # blurred copy is ready; analysis starts once a key is set (stays private meanwhile)
    result = analyse_step(o, now, analyse_fn)
    if result in ("done", "unclear", "failed", "expired"):
        _delete_original(o)  # no longer needed: only the blurred copy (if approved) remains until photo_delete_at
    return result


def process_safely(db, obs_id: int, now: datetime, redact_fn=None, analyse_fn=None) -> str:
    """Process one photo inside its own error handler, so one bad photo never blocks the others.
    An unexpected crash is rolled back and counted as a failed attempt (so it cannot retry forever)."""
    try:
        o = db.get(models.Observation, obs_id)
        if o is None:
            return "gone"
        result = process(o, now, redact_fn, analyse_fn)
        db.commit()
        return result
    except Exception as err:
        log.exception("photo %s failed", obs_id)
        db.rollback()
        try:
            o = db.get(models.Observation, obs_id)
            if o is None:
                return "gone"  # deleted meanwhile (e.g. its video was removed)
            result = record_failure(o, now, "unexpected", type(err).__name__)
            if result == "failed":
                _delete_original(o)
            db.commit()
            return result
        except Exception:
            db.rollback()
            log.exception("could not record failure for photo %s", obs_id)
            return "error"


def due(db, now: datetime, limit: int = 20) -> list[models.Observation]:
    q = select(models.Observation).where(
        or_(
            models.Observation.redaction_status.is_(None) & models.Observation.photo_path.is_not(None),
            models.Observation.redaction_status == "pending",
            (models.Observation.analysis_status == "pending") & (models.Observation.redaction_status == "done")
            & or_(models.Observation.next_attempt_at.is_(None), models.Observation.next_attempt_at <= now)
            & (bool(config.GEMINI_API_KEY)),
        )
    ).order_by(models.Observation.captured_at.desc()).limit(limit)  # freshest first: most useful for the map
    return list(db.scalars(q).all())


class PhotoWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._calls: deque[float] = deque()  # times of Gemini calls, for the per-minute cap
        self._thread = threading.Thread(target=self._run, name="photo-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _may_call(self) -> bool:
        now = time.time()
        while self._calls and now - self._calls[0] > 60:
            self._calls.popleft()
        return len(self._calls) < config.GEMINI_MAX_PER_MINUTE

    def _run(self) -> None:
        while not self._stop.wait(3):
            try:
                with SessionLocal() as db:
                    batch = [(o.id, o.redaction_status == "done" and o.analysis_status == "pending") for o in due(db, utcnow())]
                    for obs_id, needs_ai in batch:  # each photo has its own error handler (process_safely)
                        if needs_ai and not self._may_call():
                            continue  # rate limit: wait for the next minute
                        if needs_ai:
                            self._calls.append(time.time())
                        process_safely(db, obs_id, utcnow())
                        if self._stop.is_set():
                            break
            except Exception:  # e.g. database unavailable for this round
                log.exception("photo worker round failed")


worker = PhotoWorker()
