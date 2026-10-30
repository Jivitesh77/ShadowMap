"""All settings and key numbers for ShadowMap live here (see AGENTS.md §8)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///data/shadowmap.db")
    # Make relative SQLite paths relative to the backend folder, not to wherever the server was started.
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/"):
        path = BACKEND_DIR / url[len(prefix):]
        path.parent.mkdir(parents=True, exist_ok=True)
        url = prefix + str(path)
    return url


DATABASE_URL = _database_url()
DEMO_MODE = _bool("DEMO_MODE", True)
DEMO_CALL_NUMBER = os.getenv("DEMO_CALL_NUMBER", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Website addresses allowed to call the API from another origin (comma-separated). In production the frontend host
# forwards /api to the backend, so this is normally only needed for local development.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

# --- Safety score (blueprint §7) ---
SCORE_GREEN_MIN = 70
SCORE_YELLOW_MIN = 40
PHOTO_HALF_LIFE_MIN = 60

# --- Routing (blueprint §8) ---
SAFETY_COST_FACTOR = 3
MAX_DETOUR_RATIO = 1.5

# --- Sentinel photos (blueprint §5, §6) ---
PHOTO_KEEP_HOURS = 6
SNAP_RADIUS_M = 25
VIDEO_FRAME_INTERVAL_S = 5
# Walking speed for time estimates. Blueprint §8 example: 1.1 km = 13 min, i.e. about 5 km/h.
WALK_SPEED_KMH = 5.0
SAFE_PLACE_PASSED_M = 50  # a place counts as "passed" within 50 m of the route

# --- Optional Google Places (supplementary place discovery) ---
# Key only in backend/.env, never in frontend code. Empty = feature off; the app works fully without it.
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
GOOGLE_PLACES_MAX_PER_HOUR = int(os.getenv("GOOGLE_PLACES_MAX_PER_HOUR", "30"))  # protects the billing account

# --- Sentinel photos and videos ---
# Where photos and uploaded videos are stored. On a host, point DATA_DIR at a persistent disk (e.g. /var/data).
DATA_DIR = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data")))
PHOTO_DIR = DATA_DIR / "photos"  # all Sentinel images (git-ignored; deleted after PHOTO_KEEP_HOURS)
VIDEO_DIR = DATA_DIR / "videos"  # uploaded videos (assets/videos is only read, never changed)
ASSET_VIDEO_DIR = BACKEND_DIR.parent / "assets" / "videos"
START_WORKERS = _bool("START_WORKERS", True)  # background video queue; tests turn it off and run jobs directly
LIVE_MAX_GPS_ACCURACY_M = 50  # ignore readings with poorer accuracy (blueprint §20)
LIVE_DUPLICATE_RADIUS_M = 30  # blueprint §5: no new photo within ~30 m of the last one
LIVE_MAX_IMAGE_BYTES = 1_500_000
# Access code for all Sentinel endpoints except /status (photos, videos, rider routes). Only in backend/.env.
# Empty = Sentinel writes are switched off until one is set.
SENTINEL_TOKEN = os.getenv("SENTINEL_TOKEN", "").strip()
# Blueprint §5 rules, enforced by the server too (not only the browser). Switch off in .env only for daytime/on-foot testing.
SENTINEL_ENFORCE_NIGHT = _bool("SENTINEL_ENFORCE_NIGHT", True)
SENTINEL_ENFORCE_MOVING = _bool("SENTINEL_ENFORCE_MOVING", True)
NIGHT_START_HOUR, NIGHT_END_HOUR = 18, 6  # India time
MIN_MOVING_KMH = 5
MAX_PLAUSIBLE_KMH = 150  # faster than this between two photos = GPS jump or spoofed position
ORPHAN_UPLOAD_HOURS = 24  # uploaded videos never turned into a job are removed after this

# --- Gemini (route briefing now; photo analysis in M6) ---
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()  # stable, fast model (checked 2026-10-30)
GEMINI_TIMEOUT_S = 20

# --- Walk With Me (blueprint §9). Demo values are shortened, as the blueprint allows for the prototype. ---
_WALK_REAL = {"stop_s": 180, "off_route_m": 50, "off_route_s": 30, "late_s": 600, "ask_s": 60, "contacts_to_police_s": 120}
_WALK_DEMO = {"stop_s": 15, "off_route_m": 50, "off_route_s": 15, "late_s": 60, "ask_s": 20, "contacts_to_police_s": 30}
WALK_TIMERS = {k: int(os.getenv(f"WALK_{k.upper()}", v)) for k, v in (_WALK_DEMO if DEMO_MODE else _WALK_REAL).items()}
WALK_MOVE_M = 15  # moving at least this far resets the "stopped" timer
WALK_ARRIVE_M = 40  # within this of the destination = arrived
WALK_BATTERY_LOW = 10  # percent: contacts are told (not an alarm)
WALK_MAX_CONTACTS = 3
# Access code for the police dashboard (positions are shown there during alerts). Only in backend/.env.
POLICE_TOKEN = os.getenv("POLICE_TOKEN", "").strip()
