# AGENTS.md — Permanent instructions for anyone (human or AI) working on ShadowMap

Read this file fully before changing anything. Then read `docs/SPRINT_STATUS.md` to see where work stopped.

## 1. What this project is

ShadowMap is a showcase prototype: a live night-safety map of **IIIT Guwahati and the surrounding area**.
The full specification is `BLUEPRINT.md`. The build order is `docs/IMPLEMENTATION_PLAN.md`.
If they conflict, the implementation plan wins for *how* to build; the blueprint wins for *what* to build.

## 2. The project owner

- The owner (Jivitesh) is a **complete beginner** in software development.
- The AI agent is responsible for implementing the project, not for teaching programming.
- Explain every important action in plain language. Never assume the owner knows a technical term; if a term is unavoidable, explain it in one short sentence.
- Give the owner exact, copy-pasteable steps when they must do something themselves.

## 3. Hard rules (never break these)

1. **Do not delete existing assets** (`assets/`, `BLUEPRINT.md`, any file the owner added). Ask first.
2. **Do not expose API keys.** Keys live only in `backend/.env`, which is git-ignored. Never print a key, never put it in frontend code, never commit it, never paste it into docs or logs.
3. **Do not invent data.** No fake places, fake streets, fake opening hours or fake photo analyses. Map data comes from OpenStreetMap; observations come from real photos or real video. Clearly label anything that is a demo setting (e.g. the demo clock or shortened timers).
4. **Do not claim a feature works without testing it.** "Done" means its check in the implementation plan was actually run and passed. Record the evidence in `docs/SPRINT_STATUS.md`.
5. **Do not deploy anything without asking the owner.** This includes hosting, public tunnels and pushing to GitHub.
6. **Do not run destructive commands without asking** (`rm -rf`, `git reset --hard`, `git push --force`, dropping/deleting the database, overwriting data files).
7. **Do not create `CLAUDE.md`.** The owner does not want it in the project; AGENTS.md is the only instruction file.
8. **Do not start servers yourself.** The owner keeps the app running with `./start.sh`. When a check needs the running app, **tell the owner first** what you will test, then test against the owner's running servers (ports 8000 and 5173) without restarting them. The backend runs with `--reload`, so code changes apply by themselves. `pytest` and `npm run build` do not use ports and may be run any time.
9. **Never call real emergency numbers in demo mode.** Help-call buttons use a team member's number while `DEMO_MODE=true`.
10. **The AI describes places, never people.** No guessing age, gender, religion or intentions in any prompt or output.

## 4. Architecture (fixed — do not add frameworks or services)

Exactly **one frontend** and **one backend**.

| Part | Technology |
| --- | --- |
| Frontend | React + TypeScript + Vite + Tailwind CSS, in `frontend/` |
| Map display | Leaflet (`react-leaflet`) with OpenStreetMap tiles (`frontend/src/components/MapView.tsx`); tile server configurable via `VITE_TILE_URL` (`frontend/src/lib/mapProvider.ts`). Owner decision 2026-10-30: no MapLibre/OpenFreeMap/Ola/Google as primary renderer |
| Places | OSM (Overpass) + ShadowMap team-verified places in our DB, merged carefully (`backend/app/services/places.py`). Optional Google Places (`backend/app/routers/google_places.py`) only in a separate attributed list |
| Backend | Python + FastAPI, in `backend/` |
| Database | SQLite + SQLAlchemy 2 (tables in `backend/app/models.py`), file at `backend/data/shadowmap.db` |
| Routing | Our own Dijkstra in Python (`heapq`), no routing libraries |
| Vision AI + briefing | Google Gemini via the `google-genai` Python package, called **only from the backend** |
| Video frames | FFmpeg command line, called from Python with `subprocess` |
| Live updates | FastAPI WebSockets (one endpoint: `/ws`) |
| Face/plate blur | OpenCV Haar cascades (`opencv-python-headless`) |
| Voice | Browser built-in speech (`speechSynthesis`) — no paid voice service |

All five screens (Walker, Sentinel, Contact, Police dashboard, City dashboard) are pages inside the one React app.
Do **not** add: Google map tiles or a Google map, MapLibre/OpenFreeMap (removed), other paid services, Redux, Next.js, React Router, Docker, PostgreSQL, Redis, Celery, Alembic, osmnx, a separate WebSocket server, or a UI component kit — unless the owner approves.

## 5. Folder layout

```
shadowmap/
  AGENTS.md  BLUEPRINT.md  README.md  .gitignore
  backend/
    app/            FastAPI code (main.py, config.py, db.py, models.py, routers/, services/)
    scripts/        one-off tools (download OSM data, build graph, reset demo)
    tests/          pytest tests
    data/           SQLite file + photos + frames (git-ignored, generated)
    requirements.txt  .env.example  .env (secret, git-ignored)
  frontend/
    src/pages/      WalkerPage, SentinelPage, ContactPage, PolicePage, CityPage
    src/components/ shared map and UI pieces
    src/api.ts      the only place that talks to the backend
    src/lib/mapProvider.ts  which tile server the Leaflet map uses
    src/router.ts   tiny page switcher (/, /sentinel, /trip/:id, /police, /city)
  assets/
    videos/  images/  demo-data/   (owner-provided and downloaded source data; never delete)
  docs/
    SPRINT_STATUS.md  IMPLEMENTATION_PLAN.md  KNOWN_ISSUES.md
```

## 6. How to run

- First time only: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cp .env.example .env`, and `cd frontend && npm install`.
- Everything at once: `./start.sh` from the project folder (Ctrl+C stops both). Open http://localhost:5173 (this laptop only).
- Separately: backend `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000`; frontend `cd frontend && npm run dev`. Vite forwards `/api` and `/ws` to port 8000.
- Map data: `cd backend && .venv/bin/python -m scripts.build_map` (offline, from `assets/demo-data/`). `scripts.fetch_osm` downloads from Overpass only when asked.
- Backend tests: `cd backend && .venv/bin/pytest`
- Testing buttons that **write data** (reports, uploads): never on the owner's database. Use an isolated copy: `sqlite3 backend/data/shadowmap.db ".backup '<scratch>/shadowmap.db'"`, then `DATABASE_URL=sqlite:///<scratch>/shadowmap.db START_WORKERS=0 .venv/bin/uvicorn app.main:app --port 8001` and `SM_API_TARGET=http://localhost:8001 npx vite --port 5174`. Stop both afterwards.
- Frontend type-check + build: `cd frontend && npm run build`
- Tables are created automatically at backend start (`init_db`). There are no migrations: if a model changes, ask the owner before deleting `backend/data/shadowmap.db`.
- Visual check without the Chrome extension: `google-chrome-stable --headless=new --screenshot=out.png --window-size=1440,900 --virtual-time-budget=5000 http://localhost:5173/`

## 7. Working process

Schedule (owner decision, 2026-10-30): **36 h building first, then 12 h testing and fixing.** Night-ride videos may only arrive after building is finished, so features that need real footage (video mode, coloured demo map) are built and checked with test inputs during building, and verified with the real videos in the testing phase. Such features are marked "Built — real-data check pending", never "Done".

1. Work one milestone at a time, in the order of `docs/IMPLEMENTATION_PLAN.md`.
2. Before starting a milestone, mark it "In progress" in `docs/SPRINT_STATUS.md`.
3. Finish by running the milestone's **Done-when check**. Paste what was checked and the result into `docs/SPRINT_STATUS.md`.
4. Anything broken, skipped, faked-for-demo or uncertain goes into `docs/KNOWN_ISSUES.md` immediately.
5. After each milestone, stop and give the owner a short plain-language summary and ask before committing to git.
6. Keep code simple and readable. Prefer one clear file over clever abstractions. Add tests for the safety score, opening hours and routing.

Map and place rules (owner decisions, 2026-10-30):
- Map tiles are only a picture. Streets, scores, places and routes come from ShadowMap's own data; routing runs in the backend, independent of the renderer. Never claim Google-Maps-level accuracy; gaps are in `docs/DATA_GAPS.md`.
- **Never assume a place is open because hours are missing** (overrides blueprint §4's 24 h default for police/hospital/hotel). Missing = "unknown".
- **Never call a place "safe"** because of its category. Use neutral words ("place", "help point", "places passed (not closed)"). The blueprint's "nearest safe spot" is the **Help point**.
- The route briefing may only state facts from `build_facts`; AI text must pass `check_ai_text`, otherwise the labelled data summary is shown.
- **Google Places content is never drawn on the Leaflet/OSM map, never merged with our places, never stored or cached** (only place IDs may be kept; we keep none). Shown only in the separate list with "Google Maps" attribution and "Open in Google Maps" links. Key only in `backend/.env`. Without a key everything else must work.
- Team-verified places go in `assets/demo-data/manual_places.json` (who, when, how) — never copied from Google.

Sentinel security rules (audit 2026-10-30, `docs/SECURITY_AUDIT_M05_M07.md`):
- Every `/api/sentinel/*` endpoint except `/status` needs the access code (`SENTINEL_TOKEN`, header `X-Sentinel-Token`). New Sentinel endpoints must use `dependencies=PROTECTED`.
- Owner decision 2026-10-31: for the prototype, `OPEN_ACCESS=true` (set in the root `Dockerfile`) opens Sentinel and the police dashboard to everyone. New endpoints still use `PROTECTED` / `POLICE`, so turning the switch off restores the codes.
- Night and moving rules are enforced by the server, not only the browser. Never trust the browser alone for a rule.
- Photos and videos are never served without blurring (M6). `assets/videos/` is git-ignored and never modified.
- A failed job must leave nothing half-done. Every stored photo/video has a delete time, enforced by `services/retention.py` (walk personal data: 24 h after the walk).
- Deployment files exist (`render.yaml`, `backend/Dockerfile`, `frontend/vercel.json`, `docs/DEPLOYMENT.md`) but **nothing is deployed without the owner's explicit go**.
- `npm run dev` is local-only; `npm run dev:lan` exposes the app to the network — use only when needed.

## 8. Key numbers (from BLUEPRINT.md — keep them in `backend/app/config.py`, not scattered)

- Safety score 0–100; green ≥70, yellow 40–69, red ≤39.
- Photo weight `w = 0.5 ** (age_minutes / 60)`; `S = w*S_photo + (1-w)*S_map + R`.
- Route cost `length * (1 + 3 * (100 - S) / 100)`; safest route ≤ 1.5 × shortest length.
- Photos deleted after 6 hours; GPS snap radius 25 m; video frame every 5 s.
- Walk triggers (real / demo): stopped 3 min / 15 s; off-route 50 m for 30 s; "Are you safe?" 60 s to answer; then 2 min to police.
