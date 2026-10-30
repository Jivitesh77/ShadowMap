"""The ONLY way a Sentinel photo leaves the server: an approved, blurred copy that has not expired.
Originals are never served by any endpoint."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, utcnow

router = APIRouter(prefix="/api/photos")
NOT_AVAILABLE = HTTPException(404, {"code": "no_photo", "message": "No public photo for this observation."})


def is_public(o: models.Observation | None) -> bool:
    return bool(
        o and o.photo_public and o.redaction_status == "done" and o.redacted_path
        and o.photo_delete_at and o.photo_delete_at > utcnow()
    )


@router.get("/{observation_id}")
def get_photo(observation_id: int, db: Session = Depends(get_db)):
    o = db.get(models.Observation, observation_id)
    if not is_public(o):
        raise NOT_AVAILABLE  # same answer for "never existed", "not approved", "expired" and "original only"
    p = Path(o.redacted_path)
    if p.resolve().parent != config.REDACTED_DIR.resolve() or not p.is_file():
        raise NOT_AVAILABLE
    return FileResponse(p, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
