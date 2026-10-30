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

## Checked locally (without deploying)

- Production build of the frontend served from another address (port 5175) calling the backend cross-origin (port 8001) with `VITE_API_BASE`/`CORS_ORIGINS`: every page loads, access-code headers pass the CORS check, other websites are refused, no browser errors, no failed requests, phone and laptop sizes.
- First start on an empty database builds the map; a second start leaves data untouched (`build_map --if-empty`).

## Not checked

- `docker build` of the image, Render itself, Vercel itself, real https on phones, upload size limits of the hosts (very large videos may need to be trimmed or uploaded on the laptop).
