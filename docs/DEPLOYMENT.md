# Deployment (prepared, NOT done)

Nothing has been deployed. Deploying makes the app public on the internet; the owner decides when.

Plan (blueprint §18): **backend on Render** (Docker, with a persistent disk) and **frontend on Vercel**. Both give **https**, which phones need for camera and GPS.

## Why a persistent disk

Render's normal filesystem is **wiped on every deploy and restart**. SQLite stores everything in one file, and photos/uploads are files too. Without a disk, every walk, report and observation would vanish. `render.yaml` mounts a disk at `/var/data` and the backend keeps everything there (`DATA_DIR=/var/data`, `DATABASE_URL=sqlite:////var/data/shadowmap.db`). Render disks need a **paid instance** (the free type cannot have one) — confirm the price on render.com before starting. Only **one** instance may run (SQLite, background clock, duplicate lock).

## Files prepared

| File | What it does |
| --- | --- |
| `backend/Dockerfile` | Python 3.14 + FFmpeg + backend code + saved OpenStreetMap data (`assets/demo-data`). On start: builds the map only if the database is empty, then runs one uvicorn process on `$PORT`. **Not test-built yet** (Docker was not running on the laptop). |
| `.dockerignore` | Keeps `.env`, local data, the frontend and night videos out of the image. |
| `render.yaml` | Render Blueprint: Docker web service, 1 instance, health check `/api/health`, 1 GB disk at `/var/data`, environment variables (secrets marked `sync: false` = typed in the dashboard). |
| `frontend/vercel.json` | Vite build to `dist`, all paths served by the app (so `/trip/...` links work). |
| `frontend/.env.example` | `VITE_API_BASE` = backend address in production. |

## Steps (when the owner says go)

1. **Push the code to GitHub** (private repository). Check first: `git status` shows no `.env`; `assets/videos` is ignored.
2. **Render → New → Blueprint →** pick the repository. Render reads `render.yaml`.
   Fill the secret variables in the dashboard: `SENTINEL_TOKEN`, `POLICE_TOKEN` (new long random values, e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(16))"`), `GEMINI_API_KEY` (if available), `DEMO_CALL_NUMBER`, and `CORS_ORIGINS` = your Vercel address (e.g. `https://shadowmap.vercel.app`, no trailing slash).
3. Wait for the deploy; open `https://<backend>.onrender.com/api/health` → `{"status":"ok","database":"ok",...}`.
4. **Vercel → New Project →** same repository, **Root Directory `frontend`**. Add environment variable `VITE_API_BASE=https://<backend>.onrender.com`. Deploy.
5. Open the Vercel address: the header must say **Server online**. Run the [testing checklist](TESTING_CHECKLIST.md) on phones.
6. If you later change the Vercel address, update `CORS_ORIGINS` on Render.

## Storage budget (1 GB persistent disk, agreed 2026-10-30)

The Render disk (`/var/data`, 1 GB) holds the database **and** all Sentinel files.

| What | Where | Size | Removed |
| --- | --- | --- | --- |
| Uploaded video | `/var/data/videos` | **at most 250 MB** (`MAX_VIDEO_UPLOAD_MB`) | 6 h after processing; 2 h after upload if never processed |
| Video frames | `/var/data/photos` | budgeted 300 KB per frame incl. its blurred copy (`FRAME_STORAGE_BYTES`) | 6 h after processing |
| Blurred copies | `/var/data/photos/redacted` | inside the frame budget | with their photo (6 h) |
| Interrupted blurring (`.tmp`) | `/var/data/photos/redacted` | small | after 10 min |
| Upload buffer while a file arrives | system temp folder (container disk, **not** the data disk) | up to 250 MB | when the request ends |
| Database | `/var/data/shadowmap.db` | small | — |

Rules enforced by the backend:
- An upload is refused **while it arrives** once it passes 250 MB (HTTP 413). The access code is checked before any byte is read. Nothing is kept from a refused upload.
- An upload or a frame extraction is refused (HTTP 507 / job "failed" with a clear message) when less than **150 MB** (`DISK_RESERVE_MB`) would stay free. A job that stops for lack of space keeps nothing.
- Example: a 2-hour ride at one frame every 2 s is 3,600 frames ≈ 1 GB and is refused up front; at every 5 s it is 1,440 frames ≈ 420 MB. Choose the ride part (start/end) to keep jobs small.
- Abandoned uploads and frames of failed or interrupted jobs are removed by the regular cleanup (at start and every ~5 min). Files of queued/processing jobs and of kept observations are never removed by it.
- In practice the disk fits one 250 MB video plus its frames at a time; process videos one after another.

## Request limits and the client address (agreed 2026-10-31)

| Endpoint | Limit per client | Setting |
| --- | --- | --- |
| `POST /api/route` (route planning) | 30 / minute | `RATE_LIMIT_ROUTE_PER_MIN` |
| `POST /api/help-point` | 30 / minute | `RATE_LIMIT_HELP_POINT_PER_MIN` |
| `POST /api/walks` (starting a walk) | 5 / minute | `RATE_LIMIT_WALK_START_PER_MIN` |
| `POST /api/route/briefing` (AI briefing) | 10 / minute | `RATE_LIMIT_BRIEFING_PER_MIN` |
| `POST /api/reports` | 120 / **hour** per connection (plus 5 / hour per device) | `RATE_LIMIT_REPORT_PER_HOUR` |
| `GET /api/map` | 240 / minute | `RATE_LIMIT_MAP_PER_MIN` |
| `POST /api/where-am-i` | 120 / minute | `RATE_LIMIT_WHERE_AM_I_PER_MIN` |

- Over a limit: HTTP 429 with a clear message and a `Retry-After` header (seconds); the browser can read both (CORS exposes `Retry-After`). `0` switches a limit off.
- **Never limited:** position updates, PIN answers, SOS, ending a walk, the trusted-contact page, maps, police and Sentinel endpoints.
- Counts are kept **in memory**: they reset when the server restarts, and each server process counts on its own. That fits the single instance in `render.yaml`; with more instances the limits would multiply.
- **People sharing one internet connection share one allowance** (campus Wi-Fi, one phone hotspot at a demo: 30 route requests per minute for everybody together). For a demo with many phones on one hotspot, raise `RATE_LIMIT_ROUTE_PER_MIN` and `RATE_LIMIT_HELP_POINT_PER_MIN` in the Render dashboard, or set them to 0 for the demo.

**Client address behind Render's proxy.** Every request reaches the server from Render's proxy, which appends the real client address to `X-Forwarded-For`. `TRUSTED_PROXY_HOPS=1` (render.yaml) makes ShadowMap use that last, proxy-written entry only. Entries further left are written by the visitor and are ignored, so a faked header cannot dodge a limit.
- Do **not** set uvicorn's `FORWARDED_ALLOW_IPS="*"`: uvicorn would then use the *first* (visitor-written) entry.
- **Verify after the first deploy (not tested on Render yet):** the number of proxies Render puts in front is an assumption. If Render ever adds two entries for one visitor, everybody behind the same Render edge would share a limit (too strict, never too lax). Raising `TRUSTED_PROXY_HOPS` above the real number would make limits fakeable — never do that.
- Locally (`./start.sh`) the default `TRUSTED_PROXY_HOPS=0` ignores the header completely.

## Security headers and health check

- Backend (`app/security_headers.py`): `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `Permissions-Policy`, a strict `Content-Security-Policy` on API responses, `Strict-Transport-Security` over https.
- Frontend (`frontend/vercel.json`): the same basic headers; camera and location allowed for the app's own origin only.
  **No Content-Security-Policy yet** — add it after deployment, when the backend and tile addresses are known, and check
  the map, photos and API calls in a browser before keeping it.
- `/api/health` reports `database`, `video_tools` (FFmpeg), `face_blurring` (model loaded), `workers` (walk clock, video and
  photo queues alive) and `gemini_configured`. `status` is "degraded" if the database or the walk clock is down.

## Native Python on Render (alternative to Docker — deferred)

Native Python can run everything except video mode **unless FFmpeg is available**: Render's native runtime does not let
you install system packages, and whether its image includes `ffmpeg` / `ffprobe` is **not verified**. The code handles a
missing FFmpeg cleanly (video mode answers 503, everything else works) and accepts `FFMPEG_BIN` / `FFPROBE_BIN` for a
separately downloaded static build. A native setup would need: build command `cd backend && pip install -r requirements.txt`,
start command `cd backend && python -m scripts.build_map --all --if-empty && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`,
the same environment variables and persistent disk as `render.yaml`, and a Python version Render offers (tests ran on 3.14).
Not prepared as a config file: deferred by the owner (2026-10-31, prototype scope).

## Backup and restore (database, files, model)

Everything ShadowMap stores is in **one SQLite file** plus a few folders.

| What | Laptop path | Render path | Back up? |
| --- | --- | --- | --- |
| Database (walks, alerts, reports, observations, streets, places) | `backend/data/shadowmap.db` (+ `-wal` / `-shm` while running) | `/var/data/shadowmap.db` | **Yes** — the only thing that cannot be rebuilt |
| Sentinel photos (originals + `redacted/` blurred copies) | `backend/data/photos/` | `/var/data/photos/` | Usually **no**: deleted after 6 h by design, and originals show unblurred faces/plates |
| Uploaded videos | `backend/data/videos/` | `/var/data/videos/` | Usually **no**: deleted at their delete time |
| Face model (required for blurring) | `backend/models/face_detection_yunet_2023mar.onnx` | inside the image | Keep a copy; it is **git-ignored**. SHA-256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| OpenStreetMap data and city files | `assets/demo-data/` (incl. `delhi/`) | inside the image | Keep in git; the map can be rebuilt from them |
| Secrets | `backend/.env` | Render dashboard | **Never** put in a backup that is shared or uploaded |

**Back up while the app is running (safe).** The database uses WAL mode: recent changes may still sit in `shadowmap.db-wal`,
so copying `shadowmap.db` with `cp` can give an incomplete or broken copy. Use SQLite's online backup instead, which makes
a consistent copy even while the backend is writing:

```
mkdir -p ~/shadowmap-backups
sqlite3 ~/Projects/shadowmap/backend/data/shadowmap.db ".backup '$HOME/shadowmap-backups/shadowmap-$(date +%Y%m%d-%H%M).db'"
```

Without the `sqlite3` program (e.g. inside the Render container, which has Python but not the `sqlite3` tool), the same with Python:

```
python3 -c "import sqlite3,time; s=sqlite3.connect('/var/data/shadowmap.db'); d=sqlite3.connect(f'/var/data/backup-{time.strftime(\"%Y%m%d-%H%M\")}.db'); s.backup(d); d.close()"
```

(Render: run it in the service's Shell, then copy the file off the disk; how to download depends on your Render plan. **Not tested on Render.**)

**Verify a backup** (should print `ok` and sensible counts):

```
sqlite3 ~/shadowmap-backups/<file>.db "PRAGMA integrity_check;"
sqlite3 ~/shadowmap-backups/<file>.db "SELECT city, COUNT(*) FROM streets GROUP BY city; SELECT COUNT(*) FROM walks; SELECT COUNT(*) FROM reports;"
```

**Restore a backup** (replaces the current database — ask before doing this):

1. Stop the app (Ctrl+C in the `./start.sh` terminal). Never restore while the backend is running.
2. Keep the current state first: `sqlite3 backend/data/shadowmap.db ".backup 'backend/data/before-restore-$(date +%Y%m%d-%H%M).db'"`
3. Restore: `sqlite3 backend/data/shadowmap.db ".restore '$HOME/shadowmap-backups/<file>.db'"`
4. Check: `sqlite3 backend/data/shadowmap.db "PRAGMA integrity_check;"` → `ok`.
5. Start the app again (`./start.sh`). On start the backend upgrades an older backup by itself (adds missing columns and
   indexes, labels old rows with their city, numbers old walks) — it never deletes data. Open `/api/health` → `"database":"ok"`.

**Rules for backups**
- **Before every `scripts.build_map`** run and before any database change you are unsure about, make a backup.
- A backup contains **personal data**: walker names and phone numbers of walks from the last 24 h, trip routes, PIN hashes,
  report device ids and positions from the last 30 days. Keep backups on the laptop only, never in git, chat or public cloud folders. ShadowMap promises to remove
  walk details 24 h after a walk ends — **delete backups older than a few days** so that promise still holds.
- Do not include `backend/.env`, `frontend/.env*` or the photo folders in a backup you share with anyone.
- The face model is git-ignored: a host that builds from GitHub will **not** have it (photos then stay private and unscored,
  fail-closed). Before deploying, decide how the model gets into the image (see KNOWN_ISSUES #93).

## Logs and API pages when hosted

- `render.yaml` sets `API_DOCS=false`: `/docs`, `/redoc` and `/openapi.json` answer 404 on the public server; the app and `/api/health` are unaffected.
- `LOG_LEVEL=INFO`. ShadowMap's log lines look like `2026-10-30 23:05:01 WARNING shadowmap.walks: walk-1a2b3c4d5e …`. A walk is identified only by that one-way fingerprint: the walk id is the trip link's secret and never appears in ShadowMap's or uvicorn's logs. Database errors hide their stored values.
- **Not covered by ShadowMap:** Render's and Vercel's own request logs record page addresses, and the trusted contact's page address is `/trip/<walk id>`. Limit who can see those dashboards (KNOWN_ISSUES #98).

## Checked locally (without deploying)

- Production build of the frontend served from another address (port 5175) calling the backend cross-origin (port 8001) with `VITE_API_BASE`/`CORS_ORIGINS`: every page loads, access-code headers pass the CORS check, other websites are refused, no browser errors, no failed requests, phone and laptop sizes.
- First start on an empty database builds the map; a second start leaves data untouched (`build_map --all --if-empty`: each city that has no streets yet is built; a city already in use is never rebuilt).

## Not checked

- `docker build` of the image, Render itself, Vercel itself, real https on phones, upload size limits of the hosts (very large videos may need to be trimmed or uploaded on the laptop).

## Hugging Face Spaces (one container, added 2026-10-31)

`Dockerfile` in the project root builds the React app (Node 20) and runs the backend (Python 3.12, FFmpeg) in **one**
container on port 7860. The backend serves the built app from `FRONTEND_DIST` after all API routes; unknown `/api/...`
addresses stay JSON 404s. The database is **built fresh from `assets/demo-data`** inside the image — the laptop's
`backend/data/shadowmap.db` (walks, contacts, alerts) is never uploaded. Space data is lost on every restart/rebuild.
Secrets (`GEMINI_API_KEY`, optionally `SENTINEL_TOKEN`, `POLICE_TOKEN`) are set as **Space secrets**, never in files.
Without `SENTINEL_TOKEN` / `POLICE_TOKEN` the Sentinel writes and the police dashboard stay locked (safe default).
