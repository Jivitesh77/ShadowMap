# ShadowMap — Sprint Status

Update this file at the start and end of every milestone. "Done" requires the Done-when check from `IMPLEMENTATION_PLAN.md` to have been run, with the evidence written below.

Status values: Not started · In progress · Built — real-data check pending · Done (verified) · Blocked · Cut

Last updated: 2026-10-30 — M0–M4 done and verified. Next: M5 (Sentinel capture). Demo walk still to be chosen (see log).

| # | Milestone | Priority | Est. | Status | Evidence / notes |
| --- | --- | --- | --- | --- | --- |
| M0 | Project skeleton | P1 | 2 h | Done (verified) | 3/3 pytest pass; health OK direct + via proxy; all 5 pages render (screenshots); offline state checked |
| M1 | Real map data for the demo area | P1 | 3 h | Done (verified) | 72 street segments (18.2 km), 20 real OSM places; map clickable on desktop + phone |
| M2 | "Open now" + demo clock | P1 | 2 h | Done (verified) | Hours reader with 8 tests; walk-time picker (Now / Tonight 11:30 pm / any time); open/closed/unknown + basis shown |
| M3 | Safety score + street colours | P1 | 1.5 h | Done (verified) | Full §7 formula incl. photo score, freshness, reports, clamp; 11 scoring tests |
| M4 | Route finder (shortest vs safest) | P1 | 3 h | Done (verified) | Dijkstra both costs, 50% limit, comparison card; 10 routing + 1 API test; real routes on campus |
| M5 | Sentinel capture page | P1 | 3 h | Not started | |
| M6 | AI analysis, live colours, blur, deletion | P1 | 4 h | Not started | Needs Gemini key |
| M7 | Video mode | P1 | 2.5 h | Not started | Real night videos may arrive only after building; verify in the testing phase |
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

### 2026-10-30 — Owner decisions after M0
- No `CLAUDE.md` in the project (owner deleted it on purpose).
- 36 h building first, then 12 h testing/fixing. Real night videos may only be ready for the testing phase.
- Owner hit "Address already in use" on port 8000: my test servers were still running. Stopped them; ports 8000 and 5173 confirmed free.

### 2026-10-30 — M1 Real map data + M2 Open now (Done, verified)
Area: IIIT Guwahati, centre 26.0804088, 91.5605235 (OSM way 881785698, via Nominatim). Box 26.0714–26.0894 N, 91.5505–91.5705 E (~2 × 2 km), saved in `assets/demo-data/area.json`.

Built:
- `backend/scripts/fetch_osm.py`: downloads once from Overpass (retries + second server), saves `assets/demo-data/osm_2026-10-30.json` with download time, OSM timestamp, query and licence. Never overwrites.
- `backend/scripts/build_map.py`: offline; splits roads at junctions into segments, classifies roads (blueprint §7), loads places (blueprint §4 categories) + `assets/demo-data/manual_places.json` (requires verified_by + verified_on). Refuses to rebuild once observations/reports exist.
- `app/services/hours.py` (opening hours → open / closed / unknown, with basis listed / default / missing / unreadable), `geo.py`, `osm.py`.
- API: `GET /api/map?at=YYYY-MM-DDTHH:MM` (India time), `GET /api/streets/{id}` (details + places within 200 m).
- Frontend: Leaflet map with darkened OSM tiles, streets styled by road class (safety colours kept for M3), category icons with open/closed/unknown styles, white ring for manual places, dashed demo-area box, category filters with counts, "open at walk time only", walk-time picker, street and place panels, area overview with data gaps and nearest help.

Real data result (from build_map output):
- Streets: 72 segments, 18.2 km — 49 main (43 tertiary, 6 trunk/NH17), 23 residential/minor. No footpaths or lanes in OSM here.
- Places inside the box: 6 (all shops/food). Nearby help (≤ 8 km): Azara Police Station 6.7 km, Azara 30 Bedded Rural Hospital 7.5 km, Baba Ganesh Medicos 6.9 km, Indian Oil 5.5 km, 6 ATMs, 3 clinics, 2 petrol pumps.
- Only 1 of 20 places lists opening hours (South Indian Bank ATM, 24/7).

Checks run (evidence):
- `pytest`: 18 passed (hours reader 8 cases incl. past-midnight and unreadable; road classes; place categories; junction splitting; distances; map + street endpoints incl. 400/404; manual places require verifier/date/valid category).
- Live API on the owner's running server: `/api/map?at=2026-10-30T23:30` → 72 streets, 20 places; statuses: 17 unknown (missing), 2 open (default: police, hospital), 1 open (listed 24/7).
- Headless Chrome driven by script on the owner's running app, at 1440×900 and 390×844: 20 markers, 145 street paths, no sideways scrolling on phone; tapping "Azara Police Station" opens its panel (Open, assumed, 6.7 km); tapping a street opens its panel; "Tonight 11:30 pm" relabels the map; "open only" filter → 3 markers; hiding Shops & food → 14 markers.

Fixed during verification: summary crash after build (detached objects); map wider than phone screen.
Not yet seen on screen: a real manually added place (none verified yet) — logic covered by test.

### 2026-10-30 — M3 Safety score + M4 Routing (Done, verified)
Built:
- `app/services/scoring.py`: blueprint §7 map score (road class 60/45/35/25, +5 per open place ≤50 m max +15, +10 police/hospital ≤200 m), photo score (lighting 40/15/0, people 25/12/0, +5 per visible open place max 15, +5 vehicles, isolation −5/−10, hazard −5), freshness w = 0.5^(age/60), S = w·S_photo + (1−w)·S_map + R, clamp 0–100, green ≥70 / yellow 40–69 / red ≤39; §10 report effects and fade times. Safest cost = length × (1 + 3 × (100 − S)/100).
- `app/services/street_state.py`: scores every street from the database for a walk time.
- `app/services/routing.py`: graph from street segments; start/end placed on the nearest street (≤250 m); Dijkstra for shortest (length) and safest (blueprint cost); 50% detour limit with fallback; errors too_far / not_connected / same_place.
- `POST /api/route`: both routes with real distance, walking time (5 km/h), metres per colour, red metres, safe places passed (≤50 m, not closed), freshest photo age, segments, honest notes. `/api/map` and `/api/streets/{id}` now return score + breakdown.
- Frontend: streets coloured by safety score, tap-to-choose A/B, safest route (amber) and shortest (dotted, only when different), comparison card, notes, places passed, score breakdown in street panel.

Checks run (evidence):
- `pytest`: 39 passed (11 scoring, 9 routing on hand-made graphs incl. invalid point, disconnected roads, single road with no alternative, detour limit, same street, continuous geometry, negative cost; 1 route API test).
- Live API on the owner's server: campus centre → Ranjeeta (NH17) = 1250 m, 15 min, 0 m red, 2 places passed, same route (notes say so); Fancy Bazar → 422 too_far; SE road group → 422 not_connected; same point → 422 same_place; latitude 126 → 422.
- Browser test (script-driven, owner's server): tapping Start + two map points draws the route and fills the card (1.5 km, 18 min, 0 m red, 2 places); a point >250 m from streets shows the error; no sideways scrolling on phone.

Measurements on the real campus network (map data only, 23:30):
- All 73 streets score 45–64 → all yellow. Expected: without photos/reports no street can be red or green here.
- 400 random routes: 337 identical shortest/safest, 5 differ by <0.5%, 57 not connected (5-segment SE road group links to the rest only outside the download), 1 same place.
- What-if (streets on the shortest route turned dark): an alternative within +50% exists in 155 of 233 testable routes; median +3% longer. So "a street went dark → reroute" can be demonstrated on campus once Sentinel photos exist.

Demo walk: owner suggested campus → Fancy Bazar. Checked: Fancy Bazar is 20.7 km straight-line from IIIT Guwahati (OSM node 1698296623) — not walkable and far outside the map area. Owner to decide (see report).

Fixed during verification: road pieces just outside the box were dropped (now kept within ~300 m, marked outside the area); vague error title for route errors.
