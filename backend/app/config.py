"""All settings and key numbers for ShadowMap live here (see AGENTS.md §8)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _api_docs() -> bool:
    """API_DOCS: the automatic API pages /docs, /redoc and /openapi.json. Unset or empty = on (local development);
    render.yaml sets false for hosting. Only clear "on" words keep them on: a typo switches them off, never on."""
    value = os.getenv("API_DOCS", "").strip().lower()
    return value == "" or value in {"1", "true", "yes", "on"}


def _positive_int(name: str, default: int) -> int:
    """A whole number from the environment; empty, invalid or not positive = the default."""
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def _non_negative_int(name: str, default: int) -> int:
    """A whole number from the environment; 0 is allowed (= off); empty, invalid or negative = the default."""
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return value if value >= 0 else default


def rate_limits_from_env() -> dict[str, int]:
    """Requests per client in each category's window (app/rate_limit.py WINDOWS_S). 0 switches a limit off.
    Agreed 2026-10-31: route 30, help point 30, walk start 5, briefing 10 per minute. Added in the finalization and sized
    for a demo where a whole class shares one Wi-Fi / hotspot (= one client): reports 120 per hour per connection (each
    device still 5 per hour), map 240 per minute (a page uses ~1 per minute), where-am-I 120 per minute (a walk ~3)."""
    return {
        "route": _non_negative_int("RATE_LIMIT_ROUTE_PER_MIN", 30),
        "help_point": _non_negative_int("RATE_LIMIT_HELP_POINT_PER_MIN", 30),
        "walk_start": _non_negative_int("RATE_LIMIT_WALK_START_PER_MIN", 5),
        "briefing": _non_negative_int("RATE_LIMIT_BRIEFING_PER_MIN", 10),
        "report": _non_negative_int("RATE_LIMIT_REPORT_PER_HOUR", 120),
        "map": _non_negative_int("RATE_LIMIT_MAP_PER_MIN", 240),
        "where_am_i": _non_negative_int("RATE_LIMIT_WHERE_AM_I_PER_MIN", 120),
    }


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
API_DOCS = _api_docs()  # automatic API pages; off when hosted (render.yaml)
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
# Video tools. Default: found on PATH. A native (non-Docker) host can point these at a downloaded static build
# (render.yaml + scripts/fetch_ffmpeg.sh). Without them video mode answers 503; everything else keeps working.
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "").strip() or "ffmpeg"
FFPROBE_BIN = os.getenv("FFPROBE_BIN", "").strip() or "ffprobe"
# Community reports: after this many days the device id and the tapped position are removed and the report no longer
# counts anywhere (services/retention.py). Agreed with the owner on 2026-10-30.
REPORT_KEEP_DAYS = 30
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
ORPHAN_UPLOAD_HOURS = 2  # uploaded videos never turned into a job are removed after this (a 1 GB disk holds only ~3 uploads)

# --- Storage for Sentinel videos (agreed 2026-10-30: 1 GB persistent disk on Render, 250 MB per video) ---
MAX_VIDEO_UPLOAD_MB = _positive_int("MAX_VIDEO_UPLOAD_MB", 250)
MAX_VIDEO_UPLOAD_BYTES = MAX_VIDEO_UPLOAD_MB * 1024 * 1024  # largest accepted video file
UPLOAD_FORM_OVERHEAD_BYTES = 64 * 1024  # room for the form around the file (boundary, field names)
# Always left free on the data disk for the database, live photos and walks: uploads and frame extraction stop first.
DISK_RESERVE_MB = _positive_int("DISK_RESERVE_MB", 150)
# Space one video frame needs: the frame (up to ~150 KB for a portrait 640 px JPEG) plus its blurred copy. Measured
# 2026-10-30: a noisy 1080p landscape frame is ~54 KB; this estimate is deliberately generous.
FRAME_STORAGE_BYTES = 300 * 1024
ORPHAN_FILE_MIN_AGE_S = 600  # frame / blurred files nothing refers to are removed only after 10 min (never mid-write)

# --- Request limits for the expensive public endpoints (app/rate_limit.py) ---
RATE_LIMITS = rate_limits_from_env()
# How many proxies in front of the server append to X-Forwarded-For. 0 (default) = the header is ignored completely and
# the direct connection address is used. Render: 1 (its proxy appends the real client address as the last entry).
# Never set it higher than the real number of proxies: entries further left are written by the client and can be faked.
TRUSTED_PROXY_HOPS = _non_negative_int("TRUSTED_PROXY_HOPS", 0)

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

# --- M6: photo analysis and privacy ---
REDACTED_DIR = PHOTO_DIR / "redacted"  # blurred copies; the ONLY images ever served (and only when approved)
GEMINI_MAX_PER_MINUTE = int(os.getenv("GEMINI_MAX_PER_MINUTE", "10"))  # stay inside the free-tier rate limit
ANALYSIS_MAX_ATTEMPTS = 5  # then the observation is marked failed and never scored
# YuNet face detector (OpenCV model zoo, MIT licence). Checked against the official SHA-256 at every load.
YUNET_MODEL = BACKEND_DIR / "models" / "face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
YUNET_SCORE = 0.5  # lower than OpenCV's default 0.9: for privacy, blurring a non-face is better than missing a face
# Walk With Me robustness (documented in docs/KNOWN_ISSUES.md; blueprint thresholds unchanged)
WALK_MAX_ACCURACY_M = 50  # GPS fixes less accurate than this do not move the "stopped"/"off route" clocks
WALK_MAX_HOURS = 12  # a walk nobody ended stops sharing after this (then normal 24 h deletion)
WALK_PIN_MAX_FAILURES = 3  # wrong PINs before a short lock-out (stops guessing a 4-digit PIN)
WALK_PIN_LOCK_S = 30
WALK_LINK_FINAL_HOURS = 1  # after the end, the link shows only the final status for this long, then expires
