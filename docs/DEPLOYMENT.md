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
  report positions. Keep backups on the laptop only, never in git, chat or public cloud folders. ShadowMap promises to remove
  walk details 24 h after a walk ends — **delete backups older than a few days** so that promise still holds.
- Do not include `backend/.env`, `frontend/.env*` or the photo folders in a backup you share with anyone.
- The face model is git-ignored: a host that builds from GitHub will **not** have it (photos then stay private and unscored,
  fail-closed). Before deploying, decide how the model gets into the image (see KNOWN_ISSUES #93).

## Checked locally (without deploying)

- Production build of the frontend served from another address (port 5175) calling the backend cross-origin (port 8001) with `VITE_API_BASE`/`CORS_ORIGINS`: every page loads, access-code headers pass the CORS check, other websites are refused, no browser errors, no failed requests, phone and laptop sizes.
- First start on an empty database builds the map; a second start leaves data untouched (`build_map --all --if-empty`: each city that has no streets yet is built; a city already in use is never rebuilt).

## Not checked

- `docker build` of the image, Render itself, Vercel itself, real https on phones, upload size limits of the hosts (very large videos may need to be trimmed or uploaded on the laptop).
