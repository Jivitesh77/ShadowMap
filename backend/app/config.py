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

# Frontend addresses allowed to call the API during development.
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

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
