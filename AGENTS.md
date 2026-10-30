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
7. **Never call real emergency numbers in demo mode.** Help-call buttons use a team member's number while `DEMO_MODE=true`.
8. **The AI describes places, never people.** No guessing age, gender, religion or intentions in any prompt or output.

## 4. Architecture (fixed — do not add frameworks or services)

Exactly **one frontend** and **one backend**.

| Part | Technology |
| --- | --- |
| Frontend | React + TypeScript + Vite + Tailwind CSS, in `frontend/` |
| Map display | Leaflet (via `react-leaflet`) with OpenStreetMap tiles |
| Backend | Python + FastAPI, in `backend/` |
| Database | SQLite + SQLAlchemy 2 (tables in `backend/app/models.py`), file at `backend/data/shadowmap.db` |
| Routing | Our own Dijkstra in Python (`heapq`), no routing libraries |
| Vision AI + briefing | Google Gemini via the `google-genai` Python package, called **only from the backend** |
| Video frames | FFmpeg command line, called from Python with `subprocess` |
| Live updates | FastAPI WebSockets (one endpoint: `/ws`) |
| Face/plate blur | OpenCV Haar cascades (`opencv-python-headless`) |
| Voice | Browser built-in speech (`speechSynthesis`) — no paid voice service |

All five screens (Walker, Sentinel, Contact, Police dashboard, City dashboard) are pages inside the one React app.
Do **not** add: Redux, Next.js, React Router, Docker, PostgreSQL, Redis, Celery, Alembic, osmnx, a separate WebSocket server, or a UI component kit — unless the owner approves.

## 5. Folder layout

```
shadowmap/
  AGENTS.md  CLAUDE.md  BLUEPRINT.md  README.md  .gitignore
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
    src/router.ts   tiny page switcher (/, /sentinel, /trip/:id, /police, /city)
  assets/
    videos/  images/  demo-data/   (owner-provided and downloaded source data; never delete)
  docs/
    SPRINT_STATUS.md  IMPLEMENTATION_PLAN.md  KNOWN_ISSUES.md
```

## 6. How to run

- First time only: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cp .env.example .env`, and `cd frontend && npm install`.
- Backend: `cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000`
- Frontend: `cd frontend && npm run dev` (open http://localhost:5173). Vite forwards `/api` and `/ws` to port 8000.
- Backend tests: `cd backend && .venv/bin/pytest`
- Frontend type-check + build: `cd frontend && npm run build`
- Tables are created automatically at backend start (`init_db`). There are no migrations: if a model changes, ask the owner before deleting `backend/data/shadowmap.db`.
- Visual check without the Chrome extension: `google-chrome-stable --headless=new --screenshot=out.png --window-size=1440,900 --virtual-time-budget=5000 http://localhost:5173/`

## 7. Working process

1. Work one milestone at a time, in the order of `docs/IMPLEMENTATION_PLAN.md`.
2. Before starting a milestone, mark it "In progress" in `docs/SPRINT_STATUS.md`.
3. Finish by running the milestone's **Done-when check**. Paste what was checked and the result into `docs/SPRINT_STATUS.md`.
4. Anything broken, skipped, faked-for-demo or uncertain goes into `docs/KNOWN_ISSUES.md` immediately.
5. After each milestone, stop and give the owner a short plain-language summary and ask before committing to git.
6. Keep code simple and readable. Prefer one clear file over clever abstractions. Add tests for the safety score, opening hours and routing.

## 8. Key numbers (from BLUEPRINT.md — keep them in `backend/app/config.py`, not scattered)

- Safety score 0–100; green ≥70, yellow 40–69, red ≤39.
- Photo weight `w = 0.5 ** (age_minutes / 60)`; `S = w*S_photo + (1-w)*S_map + R`.
- Route cost `length * (1 + 3 * (100 - S) / 100)`; safest route ≤ 1.5 × shortest length.
- Photos deleted after 6 hours; GPS snap radius 25 m; video frame every 5 s.
- Walk triggers (real / demo): stopped 3 min / 15 s; off-route 50 m for 30 s; "Are you safe?" 60 s to answer; then 2 min to police.
