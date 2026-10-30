"""Background queue that turns night-ride videos into street observations.

One worker thread takes queued jobs one at a time, so the web server stays responsive while FFmpeg works.
Progress is saved after every frame. Frame positions come ONLY from the route the user traced (steady speed
assumed) — a video without a per-frame GPS track is never presented as having GPS positions.
"""

import logging
import threading
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app import config, models
from app.db import SessionLocal, utcnow
from app.services.routing import RouteError, StreetEdge, point_along, trace
from app.services.video import VideoError, extract_frame, frame_times, probe

log = logging.getLogger("shadowmap.video")


def street_edges(db) -> list[StreetEdge]:
    return [StreetEdge(s.id, s.start_node, s.end_node, s.length_m, s.geometry) for s in db.scalars(select(models.Street)).all()]


def frame_path(job_id: int, index: int) -> Path:
    return config.PHOTO_DIR / f"video{job_id}_f{index:05d}.jpg"


def _clear_job_output(db, job: models.VideoJob) -> None:
    """Remove observations and frame files a previous, interrupted run of this job created."""
    for o in db.scalars(select(models.Observation).where(models.Observation.video_job_id == job.id)).all():
        if o.photo_path:
            Path(o.photo_path).unlink(missing_ok=True)
        db.delete(o)
    job.frames_done = 0
    job.frames_on_streets = 0


def process_job(job_id: int) -> None:
    """Run one job to the end. Safe to call again after an interruption (starts the job over)."""
    with SessionLocal() as db:
        job = db.get(models.VideoJob, job_id)
        if not job:
            return
        _clear_job_output(db, job)
        job.status, job.stage, job.error = "processing", "checking video", None
        db.commit()
        try:
            info = probe(Path(job.file_path))
            job.video_info, job.duration_s = info, info["duration_s"]
            start = job.ride_start_s or 0.0
            end = min(job.ride_end_s or info["duration_s"], info["duration_s"])
            if end - start < job.frame_interval_s:
                raise VideoError("too_short", "The ride part of the video is shorter than one frame interval.")

            job.stage = "placing route"
            db.commit()
            route = trace(street_edges(db), [tuple(p) for p in job.route_waypoints])
            job.route_geometry, job.route_length_m = route.geometry, round(route.length_m, 1)

            times = frame_times(info["duration_s"], job.frame_interval_s, start, end)
            job.frames_total, job.stage = len(times), "extracting frames"
            db.commit()

            delete_at = utcnow() + timedelta(hours=config.PHOTO_KEEP_HOURS)
            for i, t in enumerate(times):
                out = frame_path(job.id, i)
                extract_frame(Path(job.file_path), t, out)
                fraction = (t - start) / (end - start)
                (lat, lon), street_id = point_along(route, fraction * route.length_m)
                db.add(models.Observation(
                    street_id=street_id,
                    sentinel_label=job.sentinel_label,
                    source="video",
                    captured_at=job.recorded_at + timedelta(seconds=t),
                    lat=lat,
                    lon=lon,
                    position_source="traced_route",
                    video_job_id=job.id,
                    frame_time_s=t,
                    photo_path=str(out),
                    # Video photos are kept 6 hours from processing (the ride itself may be older).
                    photo_delete_at=delete_at,
                    analysis_status="pending",
                ))
                job.frames_done = i + 1
                job.frames_on_streets = i + 1
                db.commit()

            job.status, job.stage, job.finished_at = "done", "waiting for AI analysis", utcnow()
            db.commit()
        except (VideoError, RouteError) as err:
            db.rollback()
            job = db.get(models.VideoJob, job_id)
            job.status, job.stage, job.error = "failed", None, err.message
            db.commit()
        except Exception as err:  # unexpected: record it so the job does not stay "processing" forever
            log.exception("video job %s failed", job_id)
            db.rollback()
            job = db.get(models.VideoJob, job_id)
            job.status, job.stage, job.error = "failed", None, f"Unexpected error: {type(err).__name__}"
            db.commit()


class VideoWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, name="video-worker", daemon=True)

    def start(self) -> None:
        with SessionLocal() as db:  # jobs interrupted by a restart go back in the queue
            for job in db.scalars(select(models.VideoJob).where(models.VideoJob.status == "processing")).all():
                job.status, job.stage = "queued", "restarting after interruption"
            db.commit()
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            with SessionLocal() as db:
                job = db.scalars(
                    select(models.VideoJob).where(models.VideoJob.status == "queued").order_by(models.VideoJob.id)
                ).first()
                job_id = job.id if job else None
            if job_id is None:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            process_job(job_id)


worker = VideoWorker()
