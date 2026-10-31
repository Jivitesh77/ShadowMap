"""ShadowMap backend server. Start with: uvicorn app.main:app --reload --port 8000"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, init_db, utcnow
from app.logging_setup import setup_logging
from app.security_headers import SecurityHeaders
from app.upload_guard import UploadGuard
from app.routers import map as map_router
from app.routers import google_places as google_router
from app.routers import route as route_router
from app.routers import reports as reports_router
from app.routers import sentinel as sentinel_router
from app.routers import walker as walker_router
from app.routers import dashboards as dashboards_router
from app.routers import walks as walks_router
from app.services.walk_monitor import monitor as walk_monitor
from app.services.photo_worker import worker as photo_worker
from app.routers import photos as photos_router
from app.services.video_jobs import worker as video_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # creates any missing tables
    if config.START_WORKERS:
        video_worker.start()  # background queue for night-ride videos
        walk_monitor.start()  # Walk With Me clock (alerts even if the phone goes quiet)
        photo_worker.start()  # M6: blur faces/plates, Gemini analysis, privacy approval
    yield
    video_worker.stop()
    walk_monitor.stop()
    photo_worker.stop()


setup_logging()  # before the app starts: one format, and no trip-link secrets in any log line

# The automatic API pages are for local development; hosting switches them off with API_DOCS=false (render.yaml).
_no_api_docs = {} if config.API_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="ShadowMap API", lifespan=lifespan, **_no_api_docs)
app.add_middleware(SecurityHeaders)  # nosniff, no-referrer, no framing, CSP for API responses
app.add_middleware(UploadGuard)  # video upload: size, disk space and access code checked while it arrives
app.add_middleware(  # added last = outermost, so error answers from the guard also carry CORS headers
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],  # browsers may read how long to wait after a 429 (app/rate_limit.py)
)
app.include_router(map_router.router)
app.include_router(route_router.router)
app.include_router(google_router.router)
app.include_router(sentinel_router.router)
app.include_router(reports_router.router)
app.include_router(walker_router.router)
app.include_router(walks_router.router)
app.include_router(dashboards_router.router)
app.include_router(photos_router.router)


@app.get("/")
def root():
    """The backend has no screens. Point people who open it in a browser to the app."""
    return {"message": "ShadowMap backend is running. Open the app at http://localhost:5173"}


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Is the server up and can it reach the database? Never returns secret values."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"
    from app.services import redaction
    from app.services.video import missing_video_tools
    try:
        redaction._load()
        blurring = "ok"
    except redaction.RedactionError:
        blurring = "unavailable"  # photos then stay private and unscored (fail closed)
    workers = ({"walk_clock": walk_monitor._thread.is_alive(), "video_queue": video_worker._thread.is_alive(),
                "photo_queue": photo_worker._thread.is_alive()} if config.START_WORKERS else "not started (START_WORKERS=false)")
    return {
        # "ok" needs the database and, when started, the walk clock (it raises alerts when a phone goes quiet).
        "status": "ok" if database == "ok" and (not isinstance(workers, dict) or workers["walk_clock"]) else "degraded",
        "database": database,
        "demo_mode": config.DEMO_MODE,
        "gemini_configured": bool(config.GEMINI_API_KEY),
        "video_tools": "ok" if not missing_video_tools() else "missing",
        "face_blurring": blurring,
        "workers": workers,
        "server_time_utc": utcnow().isoformat() + "Z",
    }


@app.get("/api/summary")
def summary(city: str | None = None, db: Session = Depends(get_db)):
    """Real row counts. Map, photo and report counts are for one city; walks and alerts are for all cities."""
    from app.services import cities
    city = cities.resolve(city)
    street_ids = select(models.Street.id).where(models.Street.city == city)
    place_ids = select(models.Place.id).where(models.Place.city == city)
    count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where))
    counts = {
        "city": city,
        "streets": count(models.Street, models.Street.city == city),
        "places": count(models.Place, models.Place.city == city),
        "observations": count(models.Observation, models.Observation.street_id.in_(street_ids)),
        "reports": count(models.Report, models.Report.street_id.in_(street_ids) | models.Report.place_id.in_(place_ids)),
        "walks": count(models.Walk),
        "alerts": count(models.Alert),
    }
    counts["active_walks"] = db.scalar(
        select(func.count()).select_from(models.Walk).where(models.Walk.status.in_(["active", "checking", "alert"]))
    )
    counts["open_alerts"] = db.scalar(
        select(func.count()).select_from(models.Alert).where(models.Alert.status != "resolved")
    )
    return counts
