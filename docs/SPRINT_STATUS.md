# ShadowMap — Sprint Status

Update this file at the start and end of every milestone. "Done" requires the Done-when check from `IMPLEMENTATION_PLAN.md` to have been run, with the evidence written below.

Status values: Not started · In progress · Built — real-data check pending · Done (verified) · Blocked · Cut

Last updated: 2026-10-31 — M0–M11 built; Tasks 1–8 committed in `dcbf5ea`. Finalization (prototype polish) on branch `completion/shadowmap-finalization`, uncommitted; 296 backend tests pass, browser smoke test 38/38. Docker build not verified (Task 9). Needs: Gemini key, real night footage, real Android/iPhone tests, deployment. Not production-ready.

| # | Milestone | Priority | Est. | Status | Evidence / notes |
| --- | --- | --- | --- | --- | --- |
| M0 | Project skeleton | P1 | 2 h | Done (verified) | 3/3 pytest pass; health OK direct + via proxy; all 5 pages render (screenshots); offline state checked |
| M1 | Real map data for the demo area | P1 | 3 h | Done (verified) | 72 street segments (18.2 km), 20 real OSM places; map clickable on desktop + phone |
| M2 | "Open now" + demo clock | P1 | 2 h | Done (verified) | Hours reader with 8 tests; walk-time picker (Now / Tonight 11:30 pm / any time); open/closed/unknown + basis shown |
| M3 | Safety score + street colours | P1 | 1.5 h | Done (verified) | Full §7 formula incl. photo score, freshness, reports, clamp; 11 scoring tests |
| M4 | Route finder (shortest vs safest) | P1 | 3 h | Done (verified) | Dijkstra both costs, 50% limit, comparison card; 10 routing + 1 API test; real routes on campus |
| M5 | Sentinel capture page (live) | P1 | 3 h | Done (verified) | Camera/GPS/rules/resize/upload/duplicates/status; tested with fake camera + simulated GPS and in pytest. Real phone over https: M12 |
| M6 | AI analysis, live colours, blur, deletion | P1 | 4 h | Built — real-data check pending | Redaction (YuNet + Haar), Gemini analysis + privacy check, photo endpoint, deletion, score integration; tested with synthetic images and simulated Gemini only |
| M7 | Video mode | P1 | 2.5 h | Built — real-data check pending | Full pipeline verified on a generated 120 s test clip; assets/videos was empty, so the owner's footage is untested |
| M8 | AI route briefing + voice | P1 | 2 h | Built — real-AI check pending | Data summary EN/HI verified live; AI path + fact check verified with simulated Gemini; read-aloud runs (EN/HI voices found) |
| M9 | Community reports + nearest help point | P1 | 2 h | Done (verified) | Reports change scores and routes; agreement, fading, limits; help point honest when nothing is known open |
| M10 | Walk With Me + escalation + help bar | P1 | 5 h | Done (backend verified) | UI click-through on phones in the testing phase; DEMO_CALL_NUMBER still empty |
| M11 | City dashboard + repair list | P2 | 1.5 h | Done (verified) | Ranked list, hotspots, CSV |
| M12 | Phone access (https), demo reset, README | P1 | 2.5 h | Prepared, not deployed | Render + Vercel files, README, checklists; owner decides on deployment |

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

### 2026-10-30 — Owner decision + map renderer migration (Done, verified)
- Demo area: owner accepted the recommendation — **keep the IIIT Guwahati area** (Fancy Bazar is 20.7 km away). Exact demo walk (start/end with a real alternative route) to be proposed once Sentinel data exists.
- Replaced Leaflet + OSM raster tiles with **MapLibre GL JS 6.14.0** + **OpenFreeMap dark** vector style. Only `MapView.tsx` changed its internals; its inputs stayed the same, so Walker page, panels and routing are untouched. Leaflet packages removed.
- Provider configurable: `frontend/src/lib/mapProvider.ts`, or `VITE_MAP_STYLE_URL` / `VITE_MAP_ATTRIBUTION` in `frontend/.env` (see `.env.example`).
- Our data is GeoJSON layers on top: streets by safety colour (zoom-scaled widths, dashed lanes), selection halo, invisible wide tap layer, safest route (amber, dark casing), shortest route (dotted, only when different), dashed demo-area box; places and A/B as HTML markers (same styles as before). Streets re-sent whenever scores change (ready for Sentinel updates and reports).
- Background map downloaded by our code with a 10 s limit; on failure a plain dark background is used and a notice shown — ShadowMap data still drawn.
- `docs/DATA_GAPS.md` documents measured gaps (0 footpaths, 6/73 named segments, 0 lit tags, 0 police/hospital/pharmacy/fuel inside the area, 1/20 places with hours).

Problems found and fixed during testing:
- MapLibre 6 worker file not found under the dev server's cache → set the worker address explicitly (`setWorkerUrl` with Vite `?url`); production build emits it as its own file.
- A layer filter written in a form MapLibre rejects → strict boolean filters.
- Fallback was triggered by minor loading errors and by React's development double-start → style is now fetched by our code; only a real failure counts.

Checks run (script-driven headless Chrome with WebGL, against the owner's running app; desktop 1440×900 and phone 390×844):
PASS renders (WebGL, dark style 47 layers + 8 ShadowMap layers) · PASS 72–73 ShadowMap streets drawn in safety colour · PASS 20 place markers · PASS zoom +1 via button · PASS pan by drag · PASS tap marker → place panel · PASS tap street → street panel + halo · PASS route: A/B markers, safest line drawn, comparison card, streets faded · PASS background map blocked → notice, streets and markers still drawn · PASS no JavaScript errors · PASS no sideways scrolling on phone. Backend `pytest`: 39 passed. `npm run build` passes.
Not yet checked: the production build served to a real phone (M12).

### 2026-10-30 — Back to Leaflet + multi-source places (Done, verified; Google part verified with simulated replies only)
Owner decisions: revert to Leaflet + OpenStreetMap (no MapLibre/OpenFreeMap/Ola/Google as renderer); never assume open when hours are missing; never label a place "safe" by category; optional Google Places only in a separate attributed list.

Steps (each committed): `0e0672a` Leaflet restored from 7dbb7bf (tile server configurable, dev-only test hook) · `9e44625` hours never assumed + neutral wording · `d4d319c` wider OSM discovery, careful OSM/ShadowMap matching, sources/dates/confidence · this commit: optional Google Places + docs.

Google terms checked 2026-10-30 (developers.google.com Places policies + Nearby Search docs): results without a Google map need "Google Maps" attribution; no caching except place IDs; on a map only a Google map. Implementation: backend-only call, key in header, Pro fields only (no hours), no storage, no coordinates sent to the screen, hourly cap, button-triggered.

Checks run:
- `pytest`: 50 passed (new: 6 matching/confidence tests incl. "Sharma Medicos" ≠ "Verma Medicos", "Sharma Tea Stall" ≠ "Sharma General Store", spelling variants, OSM duplicate merge, verified merge/add/explicit link; 5 Google tests with simulated replies: off without key, key only in header, no hours fields, no DB writes, no coordinates out, errors without key, hourly limit).
- New saved download `osm_2026-10-30T1233.json`: 27 places (was 20: +5 clinics via healthcare tags, +2 railway stations); still none of police/hospital/pharmacy/fuel inside the area.
- Live (owner's app): 26 of 27 places "unknown", 1 open from listed 24/7; police and hospital "unknown", confidence medium with reason; no "safe" in place data; Google status `configured: false`, search → 503 not_configured; route still 1250 m.
- Browser (desktop + phone): Leaflet + OSM tiles; no Google content on the page; 27 markers; zoom and pan; police panel shows sources, confidence + reason, "Never checked in person", OSM last-edited date; Google section says "not set up"; route card shows "Places passed (not closed)".
Not done: a live call to Google (no key).

### 2026-10-30 — M5 Live Sentinel + M7 Video mode (built and verified with generated clips; real footage pending)
`assets/videos/` was **empty**, so the owner's footage could not be tested. Everything was tested with FFmpeg-generated test-pattern clips (never used as demo data).

Built:
- Backend: `services/video.py` (ffprobe validation: allowed formats, readable, has a picture, length ≤ 2 h; reports a single location tag or recording time only if the file has them; frame extraction at 640 px), `services/video_jobs.py` (background worker thread, one job at a time, progress saved per frame, restart-safe), `routing.trace` (path along mapped streets through user-clicked points), `routers/sentinel.py` (live photo upload; asset video list/check; upload with size limit; trace preview; job create/list/detail/remove; status). New table `video_jobs`; observation fields `position_source`, `video_job_id`, `frame_time_s`, `device_id`, `analysis_error`; `init_db` now adds missing columns safely (never drops).
- Frame positions: only from the traced route, steady speed between ride start/end (optional trims). Every video observation has `position_source = traced_route` and no GPS accuracy; the screen says "not GPS readings".
- Recording time: entered by the user (India time), or the video's own stored time if present (with a warning). Never invented: a video without a stored time cannot use "video time".
- Live mode: camera + GPS permissions with plain-language errors, photo every 5–10 s, only while moving (>5 km/h) and 6 pm–6 am (both can be switched off for testing), ≥30 m between photos, GPS accuracy ≤50 m, 640 px JPEG, upload queue with retries, counts and recent log, screen kept awake where supported. Server re-checks: JPEG only, accuracy, within 25 m of a street, duplicate within 30 m.
- Photos wait with `analysis_status = pending` until Gemini (M6).

Checks run:
- `pytest`: 54 passed (Sentinel: probe/frame times/broken, renamed, audio-only and unsupported files; end-to-end job → 6 frames at 2.5…27.5 s, correct times (IST→UTC), positions moving along the route at steady speed, files written, rerun does not duplicate, remove keeps the asset video; job errors: future time, no time, no stored video time, point too far, path traversal, unsupported/broken uploads not kept, original upload name kept; live rules: saved, duplicate, inaccurate, off-street, not JPEG).
- Live on the owner's server with a generated 120 s clip: upload checked (no GPS, no stored time — reported honestly); `.py` file → 415; job over a real campus→NH17 route (1.25 km): 24 frames on 7 streets in 6.1 s; 30 health checks during processing, max 9 ms (app stayed responsive). Test job then removed (24 observations, frames and upload deleted; database back to 0 observations).
- Browser (fake camera + simulated GPS, desktop + phone): video tab (empty-assets message, trace map, job card with progress/position note), live tab (camera plays, GPS shown, photo captured and uploaded, server refusal shown with its reason, refused location permission shows a clear message), no JS errors, no sideways scrolling.

Fixed during testing: error messages with a code were shown as "Server error (422)" (also affected route errors); uploaded videos showed an internal file name; trace map tiles not darkened.
Still to do: run the owner's real night videos (testing phase); live mode on a real phone over https (M12).

### 2026-10-30 — Security and correctness audit of M5 + M7 (Done, verified)
Full report: `docs/SECURITY_AUDIT_M05_M07.md`. Tests written first: 7 of 9 failed on the old code; all pass after fixes. `pytest`: 63 passed.
Fixed: **High** — no access control + dev server on the whole network (access code on all Sentinel endpoints except status; `npm run dev` local-only, `dev:lan` opt-in). **Medium** — night and moving rules now enforced by the server; impossible GPS jumps rejected; failed video jobs leave no frames/observations; rider routes no longer public; uploaded videos get a delete time, abandoned uploads removed, `assets/videos` git-ignored. **Low** — explicit lock for duplicates (8 simultaneous uploads → 1 saved); no false GPS-jump on queued uploads.
Checked fine: photos/videos/DB/.env not downloadable (Vite /@fs → 403; backend on 127.0.0.1); delete keeps DB consistent; retention fields ready for M6.
Live checks on the owner's app: no code → 401, wrong → 403, right → 200, status public; daytime photo with the right code refused (`outside_hours`); 0 observations in the database; access screen in the browser refuses a wrong code and opens with the right one.
Owner action: restart `./start.sh` (frontend now local-only); the access code is in `backend/.env`.

### 2026-10-30 — Walker application: briefing, reports, help point, observations (verified)
Built:
- Origin/destination: tap the map, **My location** (browser GPS, plain-language errors), or **Choose a place** (campus centre + named places in the area). Walk time: Now / Tonight 11:30 pm / any time.
- **Briefing** (`POST /api/route/briefing`): route recalculated on the server; facts from real segments, places within 50 m, analysed observations and active reports. With a Gemini key: model `gemini-3.5-flash-lite` (checked 2026-10-30, configurable), JSON answer with fact ids per sentence, then a **fact check** (cited ids exist; no street/place name from the database that is not on the route; no number absent from the facts; never "safe"); one retry, else a summary built from the data. Without a key: data summary labelled "not AI". English and Hindi. Read aloud with the browser voice (stop/replay; message if no voice for the language).
- **Community reports** (`POST/GET /api/reports`, public, no free text): broken light / dark / deserted / felt unsafe / well lit (blueprint §10 points and fade times), place closed / open (counts for 3 h either side of the report). Must be within 50 m of a street; one person cannot repeat (and so cannot "agree" with themselves) within an hour; 5 per device per hour; device ids never returned. Scores, routes and open panels refresh at once.
- **Nearest help point** (`POST /api/help-point`, blueprint "nearest safe spot", renamed per owner rule 11): only places open at the walk time by listed hours or a recent report, reached by the safest route on mapped streets and drawn on the map; unknown-hours places listed separately ("may be closed"); places beyond the mapped streets listed with straight-line distance only.
- **Street details**: score breakdown, freshness ("Map data only" / "Seen N min ago"), Sentinel observations (photos hidden until blurring), active reports with fade times. Street tooltips show freshness.
- Mobile: map 56vh, big floating Help point / Report buttons that scroll to the panel, ≥40–48 px tap targets, scrollable time and filter rows.

Checks run:
- `pytest`: 71 passed (8 new: reports change scores −15 / −22.5 with two people and switch the safest route; duplicate/limit/validation; place report overrides hours only near its time; data briefing EN/HI with no outside names; AI answer accepted when correct and rejected for an off-route real place, an invented observation age, or "safe", plus Gemini errors → data summary; nearest help point never treats unknown hours as open).
- Owner's app (read-only): briefing EN/HI for campus → Ranjeeta (1.25 km, 15 min, map data only, Ranjeeta + Canteen hours unknown); help point: "No place known to be open… can be reached", nearest unknown-hours Canteen 126 m, Dhanjeet, Jonmoni; beyond streets: 3 ATMs ~2.7 km.
- All buttons on an **isolated copy** (backend 8001 on a database snapshot, frontend 5174) so the owner's data stayed unchanged (0 reports after): desktop and phone — My location, place list, comparison, briefing EN/HI + label, walk-time change, report via map tap → "score for your walk time is now 32" (phone run agreeing → 25), duplicate refused, help point, street panel with report, place "Closed now", floating buttons scroll to the panel; no JS errors; no sideways scrolling.
Fixed during testing: report reply showed the score for "now" while the page showed tonight — it now uses the page's walk time.
Not done: live Gemini (no key); Gemini photo analysis, blur, deletion (M6); real-phone test (M12).

### 2026-10-30 — M10 Walk With Me + M11 dashboards (built; backend verified; owner tests UI tomorrow)
Built: start/end walk (end needs PIN), up to 3 trusted contacts, unguessable contact link `/trip/<id>` (watch-only), private walker token, live positions (GPS or demo "simulated walk" with stand-still / off-route buttons), server clock every 2 s: stopped / off-route (checked first) / late → "Are you safe?" → contacts → police; PIN and duress PIN (looks like cancel, silently escalates; walker screen stays calm); SOS straight to police; battery-low notice; arrival "reached safely" stops sharing; link expires 1 h after the end. Help bar (112 hold 1 s, 181, nearest police, contact, fake call) — in DEMO_MODE every call rings DEMO_CALL_NUMBER only; contacts told "X is calling …". Where-am-I card. Police dashboard (POLICE_TOKEN, simulated label): active/history, reasons, live/last-moved/alert positions, route, status New→Acknowledged→Unit sent→Resolved, history. City dashboard: hotspots, ranked repair list (walks/routes through, nights dark, independent reporters), evidence (photos after blurring), CSV export. Demo timers: stop 15 s, off-route 15 s, late 60 s, ask 20 s, contacts→police 30 s (configurable).
Checks: `pytest` 79 passed (8 new incl. full 3-device escalation, duress, SOS, off-route, late without repeat, battery, arrival, PIN for end, link expiry, access control, where-am-i, repair list + CSV). Live on an isolated copy with the real background clock: ask 18 s → contacts 38 s → police 68 s; police API shows the alert; /trip, /police, /city pages load. Owner's database untouched.
Not yet done: click-through of the new screens on two phones (owner, tomorrow); DEMO_CALL_NUMBER not set; M6 (Gemini photo analysis, blur, deletion) and M12 (https for phones) still open.

### 2026-10-30 — Final integration audit and deployment preparation
Full report: `docs/FINAL_AUDIT.md`. No new features except automatic deletion (required by blueprint §6/§13, was missing).
Fixed: photos/uploads never deleted and walk personal data kept forever (critical privacy) → `services/retention.py` + test; production API address (`VITE_API_BASE`) and `CORS_ORIGINS`; `DATA_DIR`; safe first-start map build (`build_map --if-empty`).
Prepared (not deployed): `backend/Dockerfile` (Python 3.14 + FFmpeg; not test-built — Docker not running), `.dockerignore`, `render.yaml` (Docker service, 1 instance, persistent disk at /var/data), `frontend/vercel.json`, `frontend/.env.example`, `docs/DEPLOYMENT.md`.
Docs: README rewritten (setup, settings, demo script, limitations), `docs/TESTING_CHECKLIST.md` (laptop, Android Chrome, iPhone Safari, police, failure drills, showcase morning).
Checks: `pytest` 80 passed; `npm run build` passes; production build served cross-origin against an isolated backend copy — every page loads at phone and laptop size, no JS errors, no failed requests, CORS refuses other sites, trip page shows live dot + ALERT banner. Owner's database untouched.
**Not production-ready.** Open: M6 (Gemini photo analysis + blurring), real videos, real Gemini, real phones, Docker build, actual deployment.

### 2026-10-30 — M6 Gemini photo analysis and image privacy (built; NOT committed per owner)
Pipeline (`services/photo_worker.py`): original (restricted, never served) → **blur faces + plates locally** (`services/redaction.py`: YuNet face model, SHA-256-checked, on photo + brightened copy; Haar face backup; Haar plate cascades) → **Gemini analyses only the blurred copy** (`services/photo_analysis.py`: strict JSON schema, people only counted, description rejected if it describes people) and double-checks for faces/plates still visible → photo **public only if redaction succeeded and the AI saw nothing identifying** → original deleted after analysis. Any failure → kept private, never sent to the AI, never scored (fail closed). Rate limits: max GEMINI_MAX_PER_MINUTE calls, backoff 1→15 min on 429/timeout, 5 attempts then "failed".
Public photos only via `GET /api/photos/{id}` (approved + redacted + unexpired; otherwise the same 404; no-store). Street panel and city evidence show approved photos.
Reused: `retention.py` (now deletes original + blurred copy at 6 h, marks unanalysed photos "expired"), video-job deletion (removes both files), scoring formula (only `done` counts; low-confidence analyses may only lower a score).
Environment: OpenCV 5.0 was first installed but has no Haar detectors → replaced by opencv-python-headless 4.14.0.94 (verified wheel, offline install); YuNet model downloaded to a temporary folder, verified against the official checksum, copied to `backend/models/` (folder was new; nothing overwritten). Bug fixed: an unexpected detector error escaped the fail-closed path (photo stayed private but was retried forever) — every error now ends as "failed, private".
Checks: `pytest` **115 passed** (35 in test_photos.py: schema validation incl. personal-description rejection, Gemini success/no key/429/500/timeout/invalid JSON, blurring only detected regions, EXIF/GPS removed, ≤640 px, real detectors load and run, fail-closed on unreadable image/detector crash/OpenCV missing/YuNet missing or altered, approval rules, original never served, retries/give-up, no-key waiting, unclear not scored, 6-hour deletion of both files, uncertain evidence never raises a score, only `done` observations change scores). Frontend build passes.
Not verified: real Gemini (no key), detection accuracy on real night photos (synthetic images only).

### 2026-10-30 — M6 post-implementation security review (no code changed)
Confirmed: originals are never served (one image route; approval + redaction + expiry + folder checks); every redaction, Gemini, no-key, timeout and malformed-JSON path leaves photos private and unscored; only the blurred copy goes to Gemini; EXIF/GPS dropped; low-confidence evidence cannot raise a score; YuNet checksum verified; multiple faces/plates blurred.
Gaps found (to fix before real-photo validation): (1) some malformed Gemini answers (nested lists) and a vanished blurred file raise errors the worker does not count → retried forever every 3 s and, because one try block wraps the whole round, they block all other photos; (2) plate privacy relies on Gemini's check when the Russian-trained cascades find no plate — Indian plates are not covered; recommended: keep a photo private whenever vehicles are reported and no plate was blurred (and whenever people are reported and no face was blurred). Files: `app/services/photo_worker.py`, `app/services/photo_analysis.py`. Tests 115 passed; build passes.

### 2026-10-30 — M6 review fixes (uncommitted per owner)
1. Worker robustness: defensive Gemini validation (nested lists, non-text items, odd structures → controlled "invalid"); every error counts as an attempt (max 5 → failed, private, original deleted, never picked again); each photo in its own error handler (`process_safely`), so a bad photo cannot block others; missing blurred copy → failed/expired. Existing rate limit and backoff unchanged.
2. Conservative approval: public only if blurring done, analysis clear with medium/high confidence, Gemini sees no face/plate, vehicles ⇒ ≥1 plate blurred, people ⇒ ≥1 face blurred. Scoring and the briefing now use only analysed AND approved observations. Not reliable Indian plate detection (documented).
3. Retention removes abandoned `.tmp` files (>10 min) in the blurred-photo folder only.
Tests: **131 passed** (51 in test_photos.py, 16 new regression tests); frontend build passes. Files: `services/photo_analysis.py`, `services/photo_worker.py`, `services/street_state.py`, `routers/walker.py` (briefing filter), `services/retention.py`, `tests/test_photos.py`, docs.

### 2026-10-30 — Walk With Me completion (uncommitted per owner)
Already worked (verified, kept): explicit start, PIN/duress PIN (hashed), walker token (hashed), escalation stop/off-route/late → ask → contacts → police (simulated) with status flow, SOS, battery notice, arrival, background clock, 24 h deletion, police access code.
Fixed: public trip link returned the walker's phone number (removed; no phones/contacts in link view); after the end the link still showed route/timeline (now final status only, expires after 1 h) and could not be revoked (End now offers "switch the link off now" → 410 at once); repeated SOS created duplicate police alerts; GPS accuracy ignored (poor fixes no longer move the stop/off-route/arrival clocks; movement must exceed the fix uncertainty); unlimited PIN guessing (3 wrong → 30 s lock-out, contacts told); walks nobody ended shared forever (closed after 12 h, then deleted after 24 h); positions after the end were still accepted for display (now refused); briefing fact check let distances unlock invented minutes (M8 bug found by the suite).
Frontend: "Location sharing ON · last sent N s ago (± m)" status with stale warning, "End walk & stop sharing" with revoke option, SOS wording, Wake Lock (where supported), resend on reconnect/visibility, accuracy sent; contact page without phone/call button, "closed automatically" state.
Tests: **148 passed** (16 new in `tests/test_walks_privacy.py`: random links, no phone numbers, two simultaneous trips and cross-access, end/revoke/expiry, positions refused after end, inaccurate GPS, GPS jump, short signal loss, repeated SOS, duress after SOS, PIN lock-out, hashed PINs/tokens, restart, 12 h close + 24 h deletion, no trip data in public endpoints; +1 briefing regression). Frontend build passes. Isolated test database only.
Requires real devices: GPS permission flows, screen sleep/background, reconnection, battery API, Wake Lock (docs/TESTING_CHECKLIST.md). Requires deployment: https for real GPS on phones.

### 2026-10-30 — Second demo city: Aastha Kunj, Delhi (uncommitted, awaiting review)
Status: **Built and verified with real OSM data. No Sentinel footage of Delhi yet.**
- Registry `assets/demo-data/cities.json`; Delhi area `assets/demo-data/delhi/area.json`. The centre is OSM way 479658972; the box is about 4 × 4 km; landmarks were checked via Nominatim.
- Real OSM download via `scripts.fetch_osm --city delhi`: 6,375 elements, 3,993 road ways.
- Built with `scripts.build_map --city delhi`: 6,272 street pieces (394 km) and 1,442 places. Guwahati is unchanged (73 streets, 27 places). The database was backed up first, and the build is additive.
- A `city` column on streets, places and video jobs; existing rows were labelled `guwahati`. Every map, route, briefing, report, help-point, where-am-I, walk, Sentinel trace/job, city-repair and summary endpoint takes `city` (default: guwahati). Unknown city → 404.
- Performance for Delhi:
  - street↔place distances are cached per map build;
  - the help point checks the 10 nearest open + 6 unknown-hours places;
  - Leaflet draws on a canvas.
  - Measured: map ~0.5 s (first load ~1.5 s), route ~0.4 s, help point ~1.4 s.
- Routing: if the nearest path is an isolated piece, the route uses the nearest connected street within 100 m and says so.
- Frontend: a **Demo area** picker (sidebar and phone top bar) reloads the page for the chosen city; the centre and distance labels are per city.
- Checks run on an isolated database copy (backend 8001, frontend 5174, then stopped):
  - 4 Delhi routes OK. Aastha Kunj→Nehru Place metro 960 m; Lotus Temple→Kalkaji Mandir 899 m; ISKCON→East of Kailash 695 m; Aastha Kunj→Kalkaji 2.3 km, where the safest route differs.
  - The Delhi help point and where-am-I return Delhi places.
  - A Delhi report left the Guwahati summary, scores and repair list unchanged.
  - Screenshots of both cities and the Delhi city dashboard look right.
- Tests: **161 passed** (13 new in `tests/test_cities.py`). The frontend build passes.

### 2026-10-30 — Police dashboard city isolation (uncommitted, awaiting review)
- Each walk now stores `city` (the city its route was planned in). Older walks are labelled `guwahati`; the owner database had 0 walks and 0 alerts, so nothing changed there.
- `GET /api/police/alerts` (active and history) and `GET /api/police/coverage` take `city`; the default is guwahati.
- `POST /api/police/alerts/{id}/status` takes `city` too. An alert of another city answers 404 and is not changed.
- The police page sends the selected city. The escalation timing and the simulated workflow are unchanged.
- Tests: **165 passed**. There are 4 new tests in `tests/test_cities.py`:
  - each city lists only its own alerts (active and history);
  - a cross-city status update is rejected and leaves the alert unchanged;
  - the status flow still works within a city;
  - coverage is per city.
- The existing escalation and acknowledgement tests still pass. The frontend build passes.

### 2026-10-30 — Backend integration audit (excluding real photo/video validation; uncommitted)
- All 18 backend modules were inspected against the code. All 36 frontend API paths match the backend routes and methods.
- Scenarios A–I were run end-to-end on the isolated test database and all pass; they are now permanent tests in `tests/test_integration_scenarios.py`:
  - A: trip, then arrival, then sharing stops.
  - B: off-route, then the ask/contacts/police escalation.
  - C: SOS with no duplicates, then acknowledged / unit sent / resolved.
  - D: discreet duress.
  - E: connection loss and reconnect with no duplicate alerts.
  - F: two cities at once.
  - G: expiry, then anonymisation.
  - H: report, then score, repair list and CSV.
  - I: city switch.
- Defects found and reported, not fixed:
  - #87 (High): lost updates between the walk clock and requests.
  - #85 (Medium): a correct PIN reactivates a finished walk.
  - #86 (Medium, needs an owner decision): SOS after the end reopens sharing.
  - Each is reproduced by an `xfail(strict)` test.
- Lower findings: #88–#92.
- Tests: **174 passed, 3 xfailed**. The frontend build passes.

### 2026-10-30 — Reliability fixes for audit issues #85–#89 (uncommitted, awaiting review)
- #85: finished walks stay finished. Every PIN gets 409 `walk_finished`; the duress PIN still alerts police silently.
- #86 (decision B): SOS or duress PIN after the end raises one police alert (`sos_after_end` / `duress_after_end`), and the walk stays finished.
- #87: optimistic locking on `walks.version`, with `services/walks.save` retrying on the newest state. The clock, all walker endpoints, police status changes and retention use it.
- #88: missing indexes are created on start. The owner database was upgraded by the running backend; row counts are unchanged and the integrity check is ok.
- #89: backup/restore steps in DEPLOYMENT.md. The commands were tested on copies.
- Neutral wording replaces "her"/"she".
- Tests: **196 passed, 0 expected failures** (19 new in `tests/test_walk_reliability.py`; the 3 former xfails are now normal tests). The frontend build passes.

### 2026-10-30 — Visual redesign from the owner's reference screenshot (uncommitted, awaiting review)
- Light theme with a lavender-blue accent, applied to every screen through the colour tokens in `index.css`. Safety colours are unchanged; darker green and amber are used for text.
- Shell:
  - an icon-only sidebar that expands over the page on hover or keyboard focus and collapses on mouse leave;
  - a phone menu drawer that replaces the bottom tabs;
  - a top bar with search, notifications (real states only) and a profile (the name saved on this device, or "Guest"; there are no accounts).
- Walker page:
  - a planning bar (starting point / destination / travel time / Compare routes);
  - a map card with a legend;
  - route cards on the right, showing the same real numbers as the former table;
  - three shortcuts: share journey, report a concern, travel information (real route or area figures).
  - No placeholder metrics.
- Checked with headless Chrome on an isolated copy (ports 8001/5174, then stopped):
  - the sidebar goes 76 → 256 → 76 px, and the map element and its position stay unchanged;
  - planning a route shows the cards;
  - search finds real places;
  - the notifications list contains only real items;
  - the drawer navigates and closes;
  - there are no console errors.
- Screenshots were taken of both cities, the phone layout, Sentinel, the trusted-contact page and the city dashboard. The frontend build passes.

### 2026-10-30 — Sentinel video-job city isolation (backend task 1; uncommitted, awaiting review)
- `GET/DELETE /api/sentinel/videos/jobs[/{id}]` take `city` (default: Guwahati); another city's job → 404 "not found"; job responses include `city`. Access code still required first.
- Tests: **201 passed** (5 new in `tests/test_video_jobs_cities.py`, real end-to-end jobs on a generated clip in both cities). Existing Sentinel/security tests unchanged and passing.
- Frontend not changed (owner constraint): KNOWN_ISSUES #96 — the Sentinel page must send the city for the Delhi video list to work.

### 2026-10-30 — Sentinel video jobs per city in the frontend (#96; uncommitted, awaiting review)
- `frontend/src/api.ts`: `videoJobs`, `videoJob`, `deleteVideoJob` send the selected city; `lib/city.ts` `withCity` accepts an explicit city. `VideoSentinel.tsx`: list for the selected city only, loading skeleton, error message (keeps the last list), city-named empty state.
- No frontend test framework exists (adding one needs owner approval). Checked instead in headless Chrome against an isolated database copy (backend 8001 / frontend 5174, stopped and removed afterwards), with one real processed job per city from a generated test clip:
  - Delhi page lists only the Delhi job, Guwahati page only the Guwahati job;
  - switching city with the sidebar picker reloads the page and lists the new city's job;
  - deleting from the Delhi page sends `DELETE …/jobs/2?city=delhi`, shows the city-named empty state, and the Guwahati job is untouched;
  - a failing list request shows "Could not refresh the list" and the list recovers; no page errors.
- Backend 201 passed; TypeScript check and production build pass.

### 2026-10-30 — Route-use counter reliability (backend task 2; uncommitted, awaiting review)
- Root causes (reproduced by the new tests before the fix): read-modify-write increments lost counts under concurrency (40 simultaneous route requests left the first street at 8 and 11 instead of 40); two first-time writers could collide on the same new counter row; the briefing and walk start called the full route endpoint, so each also counted as a "planned" route.
- Fix: `plan_routes` (writes nothing) is separated from counting; `count_route_use` is one atomic SQLite upsert, once per street; "planned" only on `/api/route`, "walked" only on walk start; the walk is committed before its counter; a locked database costs only the count (logged), never the route or walk. No schema change, no frontend change.
- Tests: **214 passed** (13 new in `tests/test_route_use.py`; concurrency tests repeated 3 extra times). TypeScript check and production build pass.

### 2026-10-30 — Secure logging and API docs setting (task 3; uncommitted, awaiting review)
- New `backend/app/logging_setup.py`: one log format for ShadowMap's loggers, warnings/errors always visible, `LOG_LEVEL`; walk ids replaced by a one-way `walk_ref()` in our messages and in uvicorn's request log. Database errors hide stored values (`hide_parameters=True`).
- `API_DOCS` setting (unset/empty = on; anything not clearly "on" = off); `render.yaml` sets `API_DOCS=false`, `LOG_LEVEL=INFO`.
- Tests: **237 passed** (23 new in `tests/test_logging_and_docs.py`, two of them run a real uvicorn process). TypeScript check and production build pass.

### 2026-10-30 — Report retention (task 4; agreed policy 30 days; uncommitted, awaiting review)
- `config.REPORT_KEEP_DAYS = 30`. `services/retention.py` `anonymise_expired_reports`: one idempotent UPDATE clears `device_id` and sets the position to 0.0 / 0.0 for reports older than 30 days (or without a time); runs with the existing cleanup at start and every ~5 min.
- Every reader of reports (scores, place open/closed status, briefing, reports list) ignores reports older than 30 days or without a time (`street_state.retained_reports`) — before any cleanup has run, too.
- No schema change (positions cannot be empty, hence 0.0 / 0.0). The database already refuses reports without a time.
- Tests: **245 passed** (8 new in `tests/test_report_retention.py`, incl. interrupted cleanup + "restart" through the real background clock). TypeScript check and production build pass. Documentation: README "What ShadowMap keeps", DEPLOYMENT backup note, KNOWN_ISSUES #91 resolved / #99 open.

### 2026-10-31 — Video upload limits and storage cleanup (task 5; agreed 1 GB disk / 250 MB per video; uncommitted, awaiting review)
- `config`: `MAX_VIDEO_UPLOAD_MB=250`, `DISK_RESERVE_MB=150`, `FRAME_STORAGE_BYTES=300 KB` (measured frame ~54 KB landscape; generous for portrait + blurred copy), `ORPHAN_UPLOAD_HOURS` 24 → 2.
- `app/upload_guard.py` (new): access code, announced size and free space checked before the upload is read; bytes counted while arriving; 413 / 507 with clear messages. Endpoint re-checks the exact file size and removes partial files on any failure.
- `services/storage.py` (new): free-space checks; orphan cleanup of abandoned uploads and frames of failed/interrupted jobs (never queued/processing jobs or kept observations; blurred copies left to the photo rules). Runs in the regular cleanup (start + ~5 min).
- `video_jobs.process_job`: refuses (job failed, nothing kept) when the frames would not fit, and stops cleanly if the disk fills during extraction.
- Tests: `tests/conftest.py` now uses a temporary DATA_DIR (tests never touch backend/data). **259 passed** (14 new in `tests/test_video_storage.py`, one with a real server streaming 6 MB against a 1 MB limit). One unexplained failure in one earlier full run (KNOWN_ISSUES #102); 7 later runs passed. TypeScript check and production build pass.
- render.yaml: `MAX_VIDEO_UPLOAD_MB=250`, `DISK_RESERVE_MB=150`; DEPLOYMENT.md "Storage budget".

### 2026-10-31 — API rate limiting (task 6; agreed limits; uncommitted, awaiting review)
- `app/rate_limit.py` (new): in-memory sliding one-minute window per client and endpoint, thread-safe; 429 + `Retry-After`; refused attempts do not extend the wait; invalid requests count. Applied to `/api/route` (30), `/api/help-point` (30), `POST /api/walks` (5), `/api/route/briefing` (10); safety actions never limited.
- Client address: direct connection, or with `TRUSTED_PROXY_HOPS=1` (Render) the proxy-appended last `X-Forwarded-For` entry only. CORS exposes `Retry-After`.
- Settings: `RATE_LIMIT_*_PER_MIN`, `TRUSTED_PROXY_HOPS` (config, render.yaml, .env.example, README, DEPLOYMENT). The general test suite runs with very high limits (conftest).
- Tests: **274 passed** (15 new in `tests/test_rate_limits.py`, one restarting a real server). TypeScript check and production build pass. No frontend change.

### 2026-10-31 — Arrival while a safety prompt is active (task 7; agreed behaviour; uncommitted, awaiting review)
- `services/walks.py` `update_position`: an accurate fix within 40 m of the destination while the walk is "checking" or "alert" adds one `arrival_unconfirmed` timeline entry per safety episode ("…does not mean the walker is safe…"); nothing else changes. Normal arrival ("active" → "arrived") and finished walks unchanged.
- Tests: **286 passed** (12 new in `tests/test_arrival_during_prompt.py`, incl. races with PIN and SOS through the version-checked save). TypeScript check and production build pass. No frontend change.

### 2026-10-31 — Police and Sentinel access codes per browser session (task 8; uncommitted, awaiting review)
- New `frontend/src/lib/accessCodes.ts` (sessionStorage per code, one-time removal of old localStorage copies, change event); `lib/sentinelAccess.ts` uses it; `PolicePage.tsx` uses it and has "Sign out of the control room"; `SentinelPage.tsx` has "Sign out of Sentinel" and returns to its code screen when the code is cleared or refused (`api.ts` clears a refused Sentinel code).
- Headless Chrome on an isolated copy with test codes: 19 / 19 checks (migration of an old stored code, refresh, wrong codes refused, independent sign-out both ways, city switch, refused code, no codes in 973 request URLs or the console, browser restart asks for both codes again). One bug found and fixed during the check (the code screen lost its "Not accepted" message).
- TypeScript check and production build pass; backend unchanged (286 passed).

### 2026-10-31 — Task 9: Docker build and start-up check — NOT complete
- Docker is installed. The local image build exhausted available system memory and was interrupted (the Docker service was stopped during the FFmpeg package download). No image was built and no container was run, so the build, start-up, health check, docs switch, model/FFmpeg and storage checks are all still unverified (KNOWN_ISSUES #55).
- No code or Dockerfile change was made.

### 2026-10-31 — Finalization for the academic prototype (branch `completion/shadowmap-finalization`; uncommitted, awaiting review)
Scope (owner, 2026-10-31): an excellent academic prototype and live demonstration, not a production emergency platform.
- **Map and Walker page:** shapes load once, then a light scores-only refresh (`/api/map?view=scores`) with "scores updated"
  time; an older answer can no longer overwrite a newer one; busy categories (> 60 places) start hidden with an explanation;
  smaller pins when > 150 are on screen (Delhi: 287 pins instead of ~1,400); "Compare routes" never re-requests; re-plans
  are not counted (`count: false`).
- **Honest wording:** "phone reached the destination" instead of "reached safely" (timeline + contact page); places show
  "OpenStreetMap-listed" / "Needs review" / "ShadowMap verified"; Sentinel explains a missing Gemini key and a missing FFmpeg.
- **Robustness:** missing FFmpeg → 503 before an upload is read, clear job errors, health check; `/api/health` reports video
  tools, face blurring and worker threads.
- **Abuse and load:** per-connection limits for reports (120 / hour), map (240 / min), where-am-I (120 / min) — first set to 30 / 60 / 30, raised in the final review because a class sharing one hotspot counts as one client.
- **Security headers:** backend middleware; basic headers in `vercel.json` (no frontend CSP yet).
- **Accessibility / layout:** arrow keys / Home / End on all tab lists; planning bar fixed at tablet width (768 px).
- **Performance:** pages load on demand — start-up JavaScript 531 kB → 249 kB (78 kB compressed).
- **Tests:** **296 passed** (10 new in `tests/test_finalization_backend.py`); new browser smoke test `frontend/e2e/smoke.mjs`
  (no new packages) — **38 / 38** on the production build against a test copy, incl. 360 / 390 / 768 / 1440 px layouts.
- **Docs:** README, ARCHITECTURE (new), DEPLOYMENT, DATA_GAPS (verification workflow), PHOTO_PRIVACY (Sentinel record
  retention), KNOWN_ISSUES #58 #81 #97 #99 #105–#112, TESTING_CHECKLIST; historical audits marked as historical.
- **Deferred by the owner:** native-Python / Docker deployment work, trip ids in hosting logs (#98), Sentinel device-id
  retention change (documented only), accounts, SMS / WhatsApp, multi-instance, PostgreSQL, real police integration.
