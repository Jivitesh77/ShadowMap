"""Space on the data disk (DATA_DIR) for Sentinel videos, and cleanup of files nothing refers to any more.

On Render the data disk is 1 GB and also holds the database. What takes space there:
- uploaded videos (data/videos): up to MAX_VIDEO_UPLOAD_MB each, deleted 6 h after processing, or ORPHAN_UPLOAD_HOURS
  after upload if never processed;
- video frames and live photos (data/photos) and their blurred copies (data/photos/redacted): about FRAME_STORAGE_BYTES
  per frame, deleted 6 h after processing by services/retention.py;
- small .tmp files of an interrupted blurring step (removed after 10 min by services/retention.py).
The web server buffers an upload in the system temp folder while it arrives (container disk, not the data disk); the
upload guard (app/upload_guard.py) stops it at the size limit and the buffer is freed when the request ends.

Uploads and frame extraction are refused while less than DISK_RESERVE_MB would stay free, so the database always has room.
"""

import shutil
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, models

ACTIVE_JOB = ("queued", "processing")


def free_bytes(path: Path | None = None) -> int:
    """Free space on the disk that holds `path` (default: the data folder), measured on the nearest existing folder."""
    p = Path(path or config.DATA_DIR).resolve()
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def reserve_bytes() -> int:
    return config.DISK_RESERVE_MB * 1024 * 1024


def has_room(needed: int) -> bool:
    """True if `needed` more bytes still leave the reserve free on the data disk."""
    return free_bytes() - max(needed, 0) >= reserve_bytes()


def _old(f: Path, min_age_s: float) -> bool:
    try:
        return f.is_file() and time.time() - f.stat().st_mtime > min_age_s
    except OSError:
        return False


def cleanup_orphan_files(db: Session) -> dict:
    """Remove files that no job or observation refers to. Safe to run any time and repeatedly:
    - uploads: not referenced by any video job (any status), older than ORPHAN_UPLOAD_HOURS;
    - video frames: not referenced by an observation and their job is not queued / processing, older than 10 min.
    Files that are referenced (retained or approved media) are never touched here; they follow their own delete time.
    Blurred copies (photos/redacted) are left to the photo rules on purpose: they are only removed through their
    observation (services/retention.py), and an unsaved one is rewritten under the same name when the photo is retried."""
    out = {"uploads": 0, "frames": 0}
    obs_files = {Path(p).name for p in db.scalars(select(models.Observation.photo_path)).all() if p}
    if config.VIDEO_DIR.is_dir():
        used = {Path(p).name for p in db.scalars(select(models.VideoJob.file_path).where(models.VideoJob.source_kind == "upload")).all() if p}
        for f in config.VIDEO_DIR.glob("upload_*"):
            if f.name not in used and _old(f, config.ORPHAN_UPLOAD_HOURS * 3600):
                f.unlink(missing_ok=True)
                out["uploads"] += 1
    if config.PHOTO_DIR.is_dir():
        active = {j for j in db.scalars(select(models.VideoJob.id).where(models.VideoJob.status.in_(ACTIVE_JOB))).all()}
        for f in config.PHOTO_DIR.glob("video*_f*.jpg"):
            try:
                job_id = int(f.name[len("video"):f.name.index("_f")])
            except ValueError:
                continue  # not a frame name this code writes
            if job_id not in active and f.name not in obs_files and _old(f, config.ORPHAN_FILE_MIN_AGE_S):
                f.unlink(missing_ok=True)
                out["frames"] += 1
    return out
