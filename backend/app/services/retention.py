"""Deletes what ShadowMap promised not to keep (blueprint §6, §13).

- Sentinel photos: the original AND the blurred copy are deleted at `photo_delete_at` (6 h); the AI text and scores stay
  (they hold no faces). A photo deleted before it was analysed is marked "expired" and never scored.
- Uploaded videos: deleted at `file_delete_at`. Videos in assets/videos belong to the team and are never touched.
- Walks: 24 h after a walk ends, names, phone numbers, contacts, route and positions are removed.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app import config, models

WALK_KEEP_HOURS = 24
TMP_MIN_AGE_S = 600  # a blurred copy is written as .tmp for milliseconds; older .tmp files were abandoned


def _remove_file(path: str | None, allowed_dir: Path) -> None:
    """Delete a stored file; also works if the project folder moved (falls back to the file name in allowed_dir)."""
    if not path:
        return
    p = Path(path)
    for candidate in (p, allowed_dir / p.name):
        try:
            if candidate.resolve().parent == allowed_dir.resolve():
                candidate.unlink(missing_ok=True)
        except OSError:
            pass


def run(db: Session, now: datetime) -> dict:
    photos = videos = walks = 0
    for o in db.scalars(select(models.Observation).where(
            (models.Observation.photo_path.is_not(None)) | (models.Observation.redacted_path.is_not(None)),
            models.Observation.photo_delete_at <= now)).all():
        _remove_file(o.photo_path, config.PHOTO_DIR)
        _remove_file(o.redacted_path, config.REDACTED_DIR)
        o.photo_path = o.redacted_path = None
        o.photo_public = False
        if o.analysis_status == "pending":
            o.analysis_status = "expired"
        photos += 1
    for j in db.scalars(select(models.VideoJob).where(models.VideoJob.source_kind == "upload", models.VideoJob.file_delete_at.is_not(None),
                                                      models.VideoJob.file_delete_at <= now)).all():
        _remove_file(j.file_path, config.VIDEO_DIR)
        j.file_delete_at = None
        j.file_path = ""
        videos += 1
    tmp_removed = 0
    if config.REDACTED_DIR.is_dir():  # only this folder, only .tmp files, only if clearly abandoned
        for f in config.REDACTED_DIR.glob("*.tmp"):
            try:
                if f.is_file() and time.time() - f.stat().st_mtime > TMP_MIN_AGE_S:
                    f.unlink()
                    tmp_removed += 1
            except OSError:
                pass
    db.commit()  # files and photo rows first, so a busy walk below can never undo them
    cutoff = now - timedelta(hours=WALK_KEEP_HOURS)
    for w in db.scalars(select(models.Walk).where(models.Walk.ended_at.is_not(None), models.Walk.ended_at <= cutoff,
                                                  models.Walk.walker_name != "(deleted)")).all():
        w.walker_name, w.walker_phone, w.route, w.events = "(deleted)", None, [], []
        w.last_lat = w.last_lon = w.last_moved_lat = w.last_moved_lon = w.start_lat = w.start_lon = None
        w.dest_lat = w.dest_lon = 0.0
        for c in list(w.contacts):
            db.delete(c)
        for a in db.scalars(select(models.Alert).where(models.Alert.walk_id == w.id)).all():
            a.lat = a.lon = None
        walks += 1
    try:
        db.commit()
    except StaleDataError:  # a walk changed at this moment (version check): nothing overwritten, retried next run
        db.rollback()
        walks = 0
    return {"photos_deleted": photos, "videos_deleted": videos, "walks_anonymised": walks, "tmp_files_removed": tmp_removed}
