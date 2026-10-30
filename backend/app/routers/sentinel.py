"""Sentinel endpoints: live photos from a phone, and night-ride videos (blueprint §5)."""

import hmac
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, utcnow
from app.services.geo import haversine_m, locate_on_line
from app.services import cities, storage
from app.services.routing import RouteError, trace
from app.upload_guard import disk_full_detail, too_large_detail
from app.services.video import ALLOWED_EXTENSIONS, VideoError, probe
from app.services.video_jobs import street_edges, worker

router = APIRouter(prefix="/api/sentinel")
IST = timezone(timedelta(hours=5, minutes=30))


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def require_access(x_sentinel_token: str | None = Header(None)) -> None:
    """Sentinel data (photos, videos, rider routes) is only for people with the access code from backend/.env."""
    if not config.SENTINEL_TOKEN:
        raise _err(503, "no_access_code", "Sentinel is switched off: no access code is set on the server (SENTINEL_TOKEN in backend/.env).")
    if not x_sentinel_token:
        raise _err(401, "access_code_required", "Enter the Sentinel access code to use this page.")
    if not hmac.compare_digest(x_sentinel_token.encode(), config.SENTINEL_TOKEN.encode()):
        raise _err(403, "access_code_wrong", "That Sentinel access code is not correct.")


PROTECTED = [Depends(require_access)]
_photo_lock = threading.Lock()  # duplicate check + save happen as one step, even with simultaneous uploads


def now_ist() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def is_night(t: datetime) -> bool:
    return t.hour >= config.NIGHT_START_HOUR or t.hour < config.NIGHT_END_HOUR


# ---------------- Live Sentinel ----------------

@router.post("/photo", dependencies=PROTECTED)
async def live_photo(
    image: UploadFile = File(...),
    lat: float = Form(..., ge=-90, le=90),
    lon: float = Form(..., ge=-180, le=180),
    accuracy_m: float = Form(..., ge=0),
    sentinel_label: str = Form(..., min_length=1, max_length=80),
    device_id: str = Form(..., min_length=4, max_length=64),
    captured_at: str | None = Form(None),  # ISO time from the phone (UTC, ends with Z)
    heading_deg: float | None = Form(None),
    speed_kmh: float | None = Form(None),
    db: Session = Depends(get_db),
):
    data = await image.read(config.LIVE_MAX_IMAGE_BYTES + 1)
    if len(data) > config.LIVE_MAX_IMAGE_BYTES:
        raise _err(413, "image_too_large", "Photo is too large. The page should shrink it to about 640 px first.")
    if not data.startswith(b"\xff\xd8"):
        raise _err(415, "not_jpeg", "Photo must be a JPEG image.")
    if accuracy_m > config.LIVE_MAX_GPS_ACCURACY_M:
        raise _err(422, "gps_inaccurate", f"GPS accuracy is {accuracy_m:.0f} m; photos need {config.LIVE_MAX_GPS_ACCURACY_M} m or better.")
    if config.SENTINEL_ENFORCE_NIGHT and not is_night(now_ist()):
        raise _err(422, "outside_hours", "Sentinel photos are only accepted between 6 pm and 6 am.")
    if config.SENTINEL_ENFORCE_MOVING and (speed_kmh is None or speed_kmh < config.MIN_MOVING_KMH):
        raise _err(422, "not_moving", f"Photos are only taken while moving (above {config.MIN_MOVING_KMH} km/h).")

    best = None
    for s in db.scalars(select(models.Street)).all():
        d, _, point = locate_on_line(lat, lon, s.geometry)
        if best is None or d < best[0]:
            best = (d, s, point)
    if best is None or best[0] > config.SNAP_RADIUS_M:
        raise _err(422, "off_street", f"Not within {config.SNAP_RADIUS_M} m of a mapped street, so the photo was not saved.")
    _, street, _ = best

    now = utcnow()
    when = now
    phone_time = False  # True when the phone's own capture time is used (needed to judge speed between photos)
    if captured_at:
        try:
            t = datetime.fromisoformat(captured_at.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            if abs((t - now).total_seconds()) <= 600:
                when, phone_time = t, True  # trust the phone's clock only if it is within 10 minutes of ours
        except ValueError:
            pass

    with _photo_lock:
        last = db.scalars(
            select(models.Observation).where(models.Observation.device_id == device_id).order_by(models.Observation.captured_at.desc())
        ).first()
        if last:
            moved = haversine_m(lat, lon, last.lat, last.lon)
            gap_s = abs((when - last.captured_at).total_seconds())
            if moved < config.LIVE_DUPLICATE_RADIUS_M and gap_s < 600:
                raise _err(409, "duplicate", f"Less than {config.LIVE_DUPLICATE_RADIUS_M} m from this device's last photo; skipped.")
            # Only with the phone's own times: queued uploads can arrive at the server seconds apart after a signal drop.
            if phone_time and gap_s < 600 and moved / max(gap_s, 1) * 3.6 > config.MAX_PLAUSIBLE_KMH:
                raise _err(422, "gps_jump", "The position jumped further than a vehicle can travel since the last photo; skipped.")

        config.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        path = config.PHOTO_DIR / f"live_{uuid.uuid4().hex}.jpg"
        path.write_bytes(data)
        obs = models.Observation(
            street_id=street.id, sentinel_label=sentinel_label, source="live", captured_at=when, lat=lat, lon=lon,
            gps_accuracy_m=accuracy_m, heading_deg=heading_deg, speed_kmh=speed_kmh, position_source="gps",
            device_id=device_id, photo_path=str(path), photo_delete_at=when + timedelta(hours=config.PHOTO_KEEP_HOURS),
            analysis_status="pending",
        )
        db.add(obs)
        db.commit()
    return {
        "observation_id": obs.id,
        "street_id": street.id,
        "street_name": street.name or "Unnamed road",
        "snap_distance_m": round(best[0]),
        "analysis_status": "pending",
    }


# ---------------- Video mode ----------------

def _asset_path(name: str) -> Path:
    p = (config.ASSET_VIDEO_DIR / name).resolve()
    if p.parent != config.ASSET_VIDEO_DIR.resolve() or not p.is_file():
        raise _err(404, "not_found", "No such video in assets/videos.")
    return p


@router.get("/videos/assets", dependencies=PROTECTED)
def list_asset_videos():
    """Videos already in assets/videos (read in place, never changed)."""
    out = []
    if config.ASSET_VIDEO_DIR.is_dir():
        for p in sorted(config.ASSET_VIDEO_DIR.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                out.append({"name": p.name, "size_bytes": p.stat().st_size, "supported": p.suffix.lower() in ALLOWED_EXTENSIONS})
    return {"folder": "assets/videos", "videos": out}


@router.get("/videos/assets/{name}", dependencies=PROTECTED)
def check_asset_video(name: str):
    try:
        return {"video_ref": f"asset:{name}", "name": name, "info": probe(_asset_path(name))}
    except VideoError as e:
        raise _err(422 if e.code != "unsupported_format" else 415, e.code, e.message)


@router.post("/videos/uploads", dependencies=PROTECTED)
async def upload_video(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise _err(415, "unsupported_format", f"'{ext or 'no extension'}' videos are not supported. Use MP4, MOV, MKV, WEBM, AVI or 3GP.")
    config.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    # Keep the original name (made safe) after the random part, so screens can show what the user uploaded.
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename or "video").stem)[:80] or "video"
    dest = config.VIDEO_DIR / f"upload_{uuid.uuid4().hex[:12]}__{safe}{ext}"
    # The upload guard (app/upload_guard.py) already stopped oversized or unauthorised uploads while they arrived.
    # Here the exact file size is checked again while copying; any failure removes the partly written copy.
    size = 0
    try:
        with dest.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > config.MAX_VIDEO_UPLOAD_BYTES:
                    raise _err(413, "too_large", too_large_detail()["message"])
                if not storage.has_room(len(chunk)):
                    raise _err(507, "disk_full", disk_full_detail()["message"])
                f.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    try:
        info = probe(dest)
    except VideoError as e:
        dest.unlink(missing_ok=True)  # our own copy of a file we cannot use
        raise _err(415 if e.code == "unsupported_format" else 422, e.code, e.message)
    return {"video_ref": f"upload:{dest.name}", "name": file.filename or dest.name, "info": info}


def _resolve_ref(ref: str) -> tuple[Path, str, str]:
    kind, _, name = ref.partition(":")
    if kind == "asset":
        return _asset_path(name), "asset", name
    if kind == "upload":
        p = (config.VIDEO_DIR / name).resolve()
        if p.parent == config.VIDEO_DIR.resolve() and p.is_file():
            return p, "upload", name.split("__", 1)[-1]  # the original file name
    raise _err(404, "not_found", "Unknown video. Upload it or choose it from assets/videos again.")


class TraceRequest(BaseModel):
    waypoints: list[tuple[float, float]] = Field(min_length=2, max_length=60)
    city: str | None = None


@router.post("/trace", dependencies=PROTECTED)
def preview_trace(req: TraceRequest, db: Session = Depends(get_db)):
    try:
        r = trace(street_edges(db, cities.resolve(req.city)), req.waypoints)
    except RouteError as e:
        raise _err(422, e.code, e.message)
    return {"geometry": r.geometry, "length_m": round(r.length_m), "streets": len({s.edge.street_id for s in r.steps})}


class JobRequest(BaseModel):
    video_ref: str
    sentinel_label: str = Field(min_length=1, max_length=80)
    waypoints: list[tuple[float, float]] = Field(min_length=2, max_length=60)
    # India time at video second 0, e.g. 2026-10-30T23:05:00. Required unless using the video's own time.
    recorded_at_ist: str | None = None
    use_video_time: bool = False
    ride_start_s: float | None = Field(None, ge=0)
    ride_end_s: float | None = Field(None, gt=0)
    frame_interval_s: float = Field(5, ge=2, le=30)
    city: str | None = None


@router.post("/videos/jobs", dependencies=PROTECTED)
def create_job(req: JobRequest, db: Session = Depends(get_db)):
    path, kind, name = _resolve_ref(req.video_ref)
    try:
        info = probe(path)
    except VideoError as e:
        raise _err(422, e.code, e.message)
    if req.use_video_time:
        if not info["creation_time_utc"]:
            raise _err(422, "no_video_time", "This video has no recording time stored. Enter when the ride started.")
        recorded, recorded_src = datetime.fromisoformat(info["creation_time_utc"]), "video_metadata"
    else:
        if not req.recorded_at_ist:
            raise _err(422, "no_time", "Enter when the ride was recorded (India time).")
        try:
            recorded = datetime.fromisoformat(req.recorded_at_ist).replace(tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            raise _err(422, "bad_time", "Recording time must look like 2026-10-30T23:05.")
        recorded_src = "user"
    if recorded > utcnow() + timedelta(minutes=5):
        raise _err(422, "future_time", "The recording time is in the future.")
    if req.ride_end_s is not None and req.ride_start_s is not None and req.ride_end_s <= req.ride_start_s:
        raise _err(422, "bad_range", "The ride must end after it starts.")
    city = cities.resolve(req.city)
    try:
        r = trace(street_edges(db, city), req.waypoints)
    except RouteError as e:
        raise _err(422, e.code, e.message)

    job = models.VideoJob(city=city,
        original_name=name, source_kind=kind, file_path=str(path), sentinel_label=req.sentinel_label, status="queued",
        stage="waiting in queue", duration_s=info["duration_s"], frame_interval_s=req.frame_interval_s,
        ride_start_s=req.ride_start_s, ride_end_s=req.ride_end_s, recorded_at=recorded, recorded_at_source=recorded_src,
        route_waypoints=[list(p) for p in req.waypoints], route_geometry=r.geometry, route_length_m=round(r.length_m, 1),
        video_info=info, frames_done=0, frames_on_streets=0,
    )
    db.add(job)
    db.commit()
    worker.notify()
    return job_out(job, db)


def job_out(job: models.VideoJob, db: Session) -> dict:
    by_street = db.execute(
        select(models.Street.id, models.Street.name, func.count(models.Observation.id))
        .join(models.Observation, models.Observation.street_id == models.Street.id)
        .where(models.Observation.video_job_id == job.id)
        .group_by(models.Street.id)
    ).all()
    analysis = dict(db.execute(
        select(models.Observation.analysis_status, func.count()).where(models.Observation.video_job_id == job.id)
        .group_by(models.Observation.analysis_status)
    ).all())
    return {
        "id": job.id,
        "city": job.city,
        "original_name": job.original_name,
        "source_kind": job.source_kind,
        "sentinel_label": job.sentinel_label,
        "status": job.status,
        "stage": job.stage,
        "frames_total": job.frames_total,
        "frames_done": job.frames_done or 0,
        "duration_s": job.duration_s,
        "frame_interval_s": job.frame_interval_s,
        "ride_start_s": job.ride_start_s,
        "ride_end_s": job.ride_end_s,
        "recorded_at_utc": job.recorded_at.isoformat() + "Z" if job.recorded_at else None,
        "recorded_at_source": job.recorded_at_source,
        "route_geometry": job.route_geometry,
        "route_length_m": job.route_length_m,
        "video_info": job.video_info,
        "position_note": "Frame positions are estimated along the route you traced, assuming steady speed. They are not GPS readings.",
        "streets_covered": [{"street_id": sid, "name": nm or "Unnamed road", "frames": n} for sid, nm, n in by_street],
        "analysis": analysis,
        "error": job.error,
        "created_at_utc": job.created_at.isoformat() + "Z",
    }


def _job_in_city(db: Session, job_id: int, city: str) -> models.VideoJob:
    """The job, only if it belongs to `city`. Another city's job answers exactly like a missing one."""
    job = db.get(models.VideoJob, job_id)
    if not job or job.city != city:
        raise _err(404, "not_found", "No such video job in this city.")
    return job


@router.get("/videos/jobs", dependencies=PROTECTED)
def list_jobs(city: str | None = Query(None), db: Session = Depends(get_db)):
    city = cities.resolve(city)  # no city = the default city (Guwahati), like every other endpoint
    jobs = db.scalars(select(models.VideoJob).where(models.VideoJob.city == city)
                      .order_by(models.VideoJob.id.desc()).limit(20)).all()
    return {"city": city, "jobs": [job_out(j, db) for j in jobs]}


@router.get("/videos/jobs/{job_id}", dependencies=PROTECTED)
def get_job(job_id: int, city: str | None = Query(None), db: Session = Depends(get_db)):
    return job_out(_job_in_city(db, job_id, cities.resolve(city)), db)


@router.get("/status")
def sentinel_status(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(models.Observation.analysis_status, func.count()).group_by(models.Observation.analysis_status)).all())
    redaction = dict(db.execute(select(models.Observation.redaction_status, func.count()).group_by(models.Observation.redaction_status)).all())
    return {
        "observations_by_analysis": counts,
        "observations_by_redaction": {str(k or "pending"): v for k, v in redaction.items()},
        "public_photos": db.scalar(select(func.count()).select_from(models.Observation).where(models.Observation.photo_public.is_(True))),
        "ai_configured": bool(config.GEMINI_API_KEY),
        "ai_note": None if config.GEMINI_API_KEY else "Photos are blurred but wait for AI analysis until a Gemini key is set.",
    }


@router.delete("/videos/jobs/{job_id}", dependencies=PROTECTED)
def delete_job(job_id: int, city: str | None = Query(None), db: Session = Depends(get_db)):
    """Remove a processed video's frames and observations (e.g. it was traced wrongly). Files in assets/videos are never touched;
    an uploaded copy in data/videos is removed. Only jobs of the given city (default: the default city) can be removed."""
    job = _job_in_city(db, job_id, cities.resolve(city))
    if job.status in ("queued", "processing"):
        raise _err(409, "busy", "This video is still being processed. Wait until it finishes.")
    removed = 0
    for o in db.scalars(select(models.Observation).where(models.Observation.video_job_id == job.id)).all():
        for p in (o.photo_path, o.redacted_path):  # original and blurred copy
            if p:
                Path(p).unlink(missing_ok=True)
        db.delete(o)
        removed += 1
    if job.source_kind == "upload":
        p = Path(job.file_path).resolve()
        if p.parent == config.VIDEO_DIR.resolve():
            p.unlink(missing_ok=True)
    db.delete(job)
    db.commit()
    return {"deleted_job": job_id, "observations_removed": removed}
