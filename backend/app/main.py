"""ShadowMap backend server. Start with: uvicorn app.main:app --reload --port 8000"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import config, models
from app.db import get_db, init_db, utcnow
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


app = FastAPI(title="ShadowMap API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "demo_mode": config.DEMO_MODE,
        "gemini_configured": bool(config.GEMINI_API_KEY),
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
