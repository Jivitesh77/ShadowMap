# ShadowMap — Sprint Status

Update this file at the start and end of every milestone. "Done" requires the Done-when check from `IMPLEMENTATION_PLAN.md` to have been run, with the evidence written below.

Status values: Not started · In progress · Done (verified) · Blocked · Cut

Last updated: 2026-10-30 — M0 done and verified. Next: M1 (map data).

| # | Milestone | Priority | Est. | Status | Evidence / notes |
| --- | --- | --- | --- | --- | --- |
| M0 | Project skeleton | P1 | 2 h | Done (verified) | 3/3 pytest pass; health OK direct + via proxy; all 5 pages render (screenshots); offline state checked |
| M1 | Real map data for the demo area | P1 | 3 h | Not started | Owner approved going ahead with my plan; propose area box from OSM |
| M2 | "Open now" + demo clock | P1 | 2 h | Not started | |
| M3 | Map score + street colours | P1 | 1.5 h | Not started | |
| M4 | Route finder (shortest vs safest) | P1 | 3 h | Not started | |
| M5 | Sentinel capture page | P1 | 3 h | Not started | |
| M6 | AI analysis, live colours, blur, deletion | P1 | 4 h | Not started | Needs Gemini key |
| M7 | Video mode | P1 | 2.5 h | Not started | Team records night videos tonight (2026-10-30) |
| M8 | AI route briefing + voice | P1 | 2 h | Not started | Needs Gemini key |
| M9 | Community reports + nearest safe spot | P1 | 2 h | Not started | |
| M10 | Walk With Me + escalation + help bar | P1 | 5 h | Not started | Needs team member's demo phone number |
| M11 | City dashboard + repair list | P2 | 1.5 h | Not started | |
| M12 | Phone access (https), demo reset, README | P1 | 2.5 h | Not started | Needs owner's choice of https method |

## Log

### 2026-10-30 — Planning (Phase 0)
- Inspected repository: `BLUEPRINT.md` (750 lines) and empty folders `assets/videos`, `assets/images`, `assets/demo-data`, `docs`. No commits yet on branch `master`; no git remote.
- Checked tools: Python 3.14.8, pip 26.2.1, uv 0.5.9, Node.js 26.12.0, npm 12.2.1, Git 2.56.0, FFmpeg/ffprobe 9.0.2, sqlite3 3.54.0. All present.
- Created: `AGENTS.md`, `CLAUDE.md`, `.gitignore`, `docs/IMPLEMENTATION_PLAN.md`, `docs/SPRINT_STATUS.md`, `docs/KNOWN_ISSUES.md`.
- No code written, no packages installed, nothing committed or deployed.

### 2026-10-30 — M0 Project skeleton (Done, verified)
Owner decisions: ignore the missing BUILD_PLAN.md; follow my plan; use SQLAlchemy; team records night videos tonight.

Built:
- Backend (`backend/`): Python 3.14 virtual environment; FastAPI 0.162, SQLAlchemy 2.1.6, uvicorn 0.54; `config.py` (settings + blueprint numbers), `db.py` (engine, WAL mode, foreign keys), `models.py` (streets, places, observations, reports, walks, contacts, alerts), `main.py` (`GET /api/health`, `GET /api/summary` with real row counts; CORS for localhost:5173). `.env.example` + local `.env` (git-ignored, no secrets yet).
- Frontend (`frontend/`): Vite 8.3, React 19.3, TypeScript 7.0, Tailwind 4.3, Leaflet 1.9 + react-leaflet 5 (installed, not used yet), Inter font bundled locally. Responsive shell: sidebar on laptop, top bar + bottom tabs on phone; pages Walker, Sentinel, Trusted contact (/trip and /trip/:id), Police, City, 404. Shared loading skeletons, error state with Retry, empty states. Live server status (server/database/AI key yes-no) and demo-mode banner. Vite proxy forwards /api and /ws to the backend.

Checks run (evidence):
- `pytest -v`: test_health_reports_ok_and_hides_secrets PASSED, test_summary_counts_tables PASSED, test_rows_survive_reconnect PASSED (writes all 7 tables, closes the DB, reopens, reads back).
- `curl localhost:8000/api/health` and via `localhost:5173/api/health` → `{"status":"ok","database":"ok","demo_mode":true,"gemini_configured":false,...}`.
- Real DB file `backend/data/shadowmap.db` created with all 7 tables (`sqlite3 .tables`), still present after a server restart.
- `npm run build`: type-check passes, production build succeeds.
- Headless Chrome screenshots at 1440×900 and 390×844 of every page: render correctly, show live counts (all 0, real).
- Backend stopped on purpose → pages show "Server offline", red error with Retry, and "Can't check for alerts" (not a false "No alerts"); backend restarted → pages reconnected by themselves.

Fixed during verification: fallback font rendered as monospace (now bundled Inter); misplaced "in development" tag; police/city panels claimed "no alerts/repairs" while offline.
