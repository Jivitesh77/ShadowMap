# ShadowMap

A showcase **prototype** of a night-safety map for **IIIT Guwahati and the surrounding area**.
It colours streets by how safe they look at night, compares the shortest and the safest walking route, explains the route in plain words (English or Hindi), lets a trusted contact follow a walk live, and escalates to a (simulated) police dashboard if the walker stops answering.

> **This is not production software.** It is a student prototype for a showcase. It has not been security-audited by a third party, has no user accounts, uses shared access codes, and the police integration is simulated. Do not rely on it for anyone's real safety.

Specification: [BLUEPRINT.md](BLUEPRINT.md) · Progress: [docs/SPRINT_STATUS.md](docs/SPRINT_STATUS.md) · Known issues: [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) · Map data gaps: [docs/DATA_GAPS.md](docs/DATA_GAPS.md) · Final audit: [docs/FINAL_AUDIT.md](docs/FINAL_AUDIT.md) · Manual tests: [docs/TESTING_CHECKLIST.md](docs/TESTING_CHECKLIST.md) · Deployment: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## What works (and how far it was tested)

| Part | State |
| --- | --- |
| Map of the area (Leaflet + OpenStreetMap), place markers, open / closed / hours unknown | Working, tested |
| Street safety scores, shortest vs safest route (Dijkstra), comparison | Working, tested |
| Community reports (change scores and routes), nearest help point | Working, tested |
| Route briefing EN/HI + read aloud | Working as a **data summary**; the Gemini-written version is tested only with simulated answers (no key yet) |
| Sentinel live photos + video mode (FFmpeg, background queue) | Working with generated test clips; **owner's night videos not yet run**; live camera not yet tried on a real phone. Without FFmpeg the server says "video mode unavailable" (503) and everything else keeps working; without a Gemini key the page says photos stay blurred and private |
| Gemini photo analysis, face/plate blurring, photo display (M6) | Built: local blurring (YuNet + Haar), Gemini analysis of blurred copies, fail-closed approval, 6-h deletion. Tested with synthetic images and simulated Gemini only; needs a Gemini key and real night photos. See [docs/PHOTO_PRIVACY.md](docs/PHOTO_PRIVACY.md) |
| Walk With Me (stop / off-route / late / battery → Are you safe? → contacts → police; PIN, duress PIN, SOS, help bar, Where am I; end & stop sharing, revoke link) | **Implemented and tested** in the backend (lifecycle, escalation, access control, revocation/expiry, GPS accuracy, duplicate alerts, PIN lock-out, deletion) incl. the live background clock. **Police: implemented but simulated.** **Needs real Android/iPhone testing** (GPS, screen sleep, background) |
| Contact trip page, police dashboard (simulated), city dashboard + CSV | Working; browser smoke test (`frontend/e2e/smoke.mjs`, 38 checks incl. 360/390/768/1440 px layouts) on the production build. **Not tried on real phones / Safari** |
| Automatic deletion (photos 6 h, uploaded videos 6 h, walk personal data 24 h after the walk, report device ids and positions after 30 days — see below) | Working, tested |

## Run it on your laptop

You need Python 3.12+ (tested on 3.14), Node.js 20+ (tested on 26), FFmpeg, and Git.

**First time only:**
```bash
cd ~/Projects/shadowmap/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill in the values you have (see below)
.venv/bin/python -m scripts.build_map --if-empty

cd ~/Projects/shadowmap/frontend
npm install
```

**Every time:**
```bash
cd ~/Projects/shadowmap
./start.sh
```
Open **http://localhost:5173** (this laptop only). `Ctrl + C` stops everything.
For phones on the same Wi-Fi, see [docs/TESTING_CHECKLIST.md](docs/TESTING_CHECKLIST.md) section 0 (camera and GPS still need https).

## Settings (environment variables)

Secrets live **only** in `backend/.env` (git-ignored) or in the hosting dashboard — never in frontend code, chat or git.
Full lists with comments: [backend/.env.example](backend/.env.example) and [frontend/.env.example](frontend/.env.example).

| Variable | Where | Purpose |
| --- | --- | --- |
| `SENTINEL_TOKEN` | backend | Access code for the Sentinel page (photos, videos, rider routes). Required. |
| `POLICE_TOKEN` | backend | Access code for the police dashboard. Required. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | backend | AI briefing (and M6 photo analysis). Optional: without it a labelled data summary is used. |
| `GOOGLE_PLACES_API_KEY` | backend | Optional extra place list (separate panel, never on the map, never stored). Costs money. |
| `DEMO_MODE` | backend | `true`: shortened walk timers; help-call buttons ring `DEMO_CALL_NUMBER`, **never** 112/181/100. |
| `API_DOCS` | backend | Automatic API pages `/docs`, `/redoc`, `/openapi.json`. Empty = on (local); `false` when hosted (`render.yaml`). |
| `LOG_LEVEL` | backend | `INFO` (default), `DEBUG` or `WARNING`; warnings and errors always show. Logs never contain trip-link ids, names, phones or positions. |
| `RATE_LIMIT_*` | backend | Requests per client: route 30, help point 30, walk start 5, briefing 10, map 240, where-am-I 120 per minute; reports 120 per hour per connection (plus 5 per hour per device). `0` = off. Over a limit: 429 + `Retry-After`. Details: docs/DEPLOYMENT.md. |
| `FFMPEG_BIN`, `FFPROBE_BIN` | backend | Video tools (default: found on `PATH`). Missing → video mode answers 503; the rest of the app works. |
| `TRUSTED_PROXY_HOPS` | backend | `0` locally (ignore `X-Forwarded-For`); `1` on Render. |
| `DEMO_CALL_NUMBER` | backend | A team member's phone for demo help calls. Empty = buttons dial nothing. |
| `SENTINEL_ENFORCE_NIGHT`, `SENTINEL_ENFORCE_MOVING` | backend | Blueprint capture rules, enforced by the server. `false` only while testing in daytime / on foot. |
| `DATA_DIR`, `DATABASE_URL` | backend | Where the database, photos and uploads live (a persistent disk when hosted). |
| `CORS_ORIGINS` | backend | Frontend address(es) allowed to call the backend when hosted separately. |
| `WALK_STOP_S`, `WALK_ASK_S`, `WALK_CONTACTS_TO_POLICE_S`, … | backend | Override Walk With Me timers (seconds). |
| `VITE_API_BASE` | frontend | Backend address when hosted (empty locally). |
| `VITE_TILE_URL`, `VITE_TILE_ATTRIBUTION` | frontend | Optional other tile server (never Google tiles). |

Show an access code: `grep SENTINEL_TOKEN ~/Projects/shadowmap/backend/.env` (or `POLICE_TOKEN`). Changes to `.env` need a restart of `./start.sh`.

## Map data

Real OpenStreetMap data, downloaded once and saved in `assets/demo-data/` — the demo never downloads it again.
- Add a place the team checked in person: edit `assets/demo-data/manual_places.json` (instructions inside), then `cd backend && .venv/bin/python -m scripts.build_map` (only possible before any Sentinel photos or reports exist).
- Fresh OpenStreetMap download (rarely needed): `.venv/bin/python -m scripts.fetch_osm`, then `build_map`.

### Two demo cities

| City | Area | Data folder |
| --- | --- | --- |
| **IIIT Guwahati** (default) | ~2 × 2 km around the campus | `assets/demo-data/` |
| **Aastha Kunj, Delhi** | ~4 × 4 km around Aastha Kunj Park (Lotus Temple, ISKCON, Kalkaji Mandir, Nehru Place, East of Kailash) | `assets/demo-data/delhi/` |

- **Switch city:** use the **Demo area** menu at the bottom of the left sidebar (on phones, the menu in the top bar). The page reloads, then the map, scores, places, reports, routes, help point and dashboards all belong to the chosen city. You can also open a link such as `http://localhost:5173/?city=delhi`. Switching is disabled during a Walk With Me walk.
- Each city has its own streets, places and routing network. A report or photo always belongs to one street, so it can never appear in the other city.
- **Build one city:** `cd backend && .venv/bin/python -m scripts.build_map --city delhi`. Use `--all` to build every city. A city that already has reports or photos is never rebuilt.
- **Download one city again:** `.venv/bin/python -m scripts.fetch_osm --city delhi`.
- **Delhi demo routes** (tap these points on the map, or use "Choose a place"):
  1. Aastha Kunj Park → Nehru Place metro station (~960 m)
  2. Lotus Temple → Kalkaji Mandir (~900 m)
  3. ISKCON → East of Kailash (~700 m)
  4. Aastha Kunj Park → Kalkaji residential area (~2.3 km). On this route, the safest route differs from the shortest.
- Delhi data sources, counts and gaps: [docs/DATA_GAPS.md](docs/DATA_GAPS.md) (second half).

## Demo instructions (blueprint §16, about 5 minutes)

**Before:** section 6 of the [testing checklist](docs/TESTING_CHECKLIST.md). Set `DEMO_CALL_NUMBER`. Charge phones. If hosted, open the site 10 minutes early.
**Roles:** presenter, laptop operator (map + police + city dashboards), walker phone, contact phone.

1. **Walker → "Tonight 11:30 pm".** Coloured streets; places show *open / closed / hours unknown* (never assumed open).
2. **Route tab:** A = "IIIT Guwahati (campus centre)", B = a place (e.g. Ranjeeta). Show shortest vs safest.
3. **Hear the briefing** in English, then हिन्दी. Point out its label (AI fact-checked, or "data summary, not AI").
4. **Report tab** (or a judge on their phone): "Dark here" on a street of the route → it turns red; route and briefing update.
5. **Start Walk With Me** on the walker phone (contact = roommate, PIN, duress PIN, tick *simulate walk*); share the link to the contact phone.
6. **Help bar:** 112 (hold), 181, Police, Fake call — in demo mode it rings the team phone and tells the contact.
7. **"Demo: stand still"** → 15 s: *Are you safe?* → no answer → 20 s: **contact phone turns red** → 30 s: **police dashboard** alert with live position and route. Acknowledged → Unit sent.
8. Enter the **PIN** → resolved, contact sees "False alarm". (Optional: duress PIN — walker screen stays calm, contact and police see DURESS.)
9. **City dashboard:** the reported street in the ranked repair list; Download CSV.
10. Close: *"Google Maps knows the shortest way home. ShadowMap knows the safest way home, as of ten minutes ago."* Be honest: photo analysis runs only with a Gemini key, and face/plate detection has not been measured on real night photos (Indian plates especially).

## What ShadowMap keeps, and for how long

Cleanup runs automatically in the backend (at start and about every 5 minutes), so it also catches up after the server was off.

| Data | Kept | After that |
| --- | --- | --- |
| Sentinel photos (original and blurred copy) | 6 hours | Files deleted; the AI's text and scores stay (no faces) |
| Uploaded ride videos | 6 hours after processing (24 h if never used) | File deleted |
| Walk With Me: name, phone, contacts, route, positions | Until 24 h after the walk ends | Removed; the walk record keeps only its status and times |
| Community reports: device id and the exact tapped position | **30 days** | Device id removed, position replaced by 0.0 / 0.0 ("removed"). The type, the street or place, and the time stay as history and no longer count anywhere |
| Community reports' effect on scores | 2 hours to 7 days depending on type | Report fades out (never longer than 30 days) |

Automated tests check these rules on a test database; they do not by themselves make the app compliant with any privacy law. Backups keep data longer — delete them after a few days (docs/DEPLOYMENT.md).

## Known limitations (full list: docs/KNOWN_ISSUES.md)

- **Photo analysis needs a Gemini key:** without it photos are blurred but stay private and do not affect scores. Only analysed **and** privacy-approved photos count. Conservative rule: photos with vehicles where no plate was blurred stay private; Indian plate detection is not reliable, so expect many night photos to stay private. Detection accuracy on real photos is unmeasured.
- **Delhi has no Sentinel photos and no team-checked places yet:** every Delhi score is a map-only baseline, and most places show "Hours unknown" at night (only 139 of 1,442 list hours). With ~1,400 markers the Delhi map is busy; hide "Shops & food" with its chip.
- **Thin OpenStreetMap data around campus:** no footpaths, 6 of 73 street segments named, no police/hospital/pharmacy/petrol pump inside the area, 1 of 27 places lists opening hours. Nothing is invented.
- **Police integration is simulated.** No SMS/WhatsApp: contacts see alerts on the trip page only, and only if they keep it open.
- **Browsers may pause a page in the background** (screen off, app switched, especially on iPhone). Positions then stop; the server treats that like "stopped" and asks/escalates. Background tracking is **not** guaranteed.
- **Anyone holding a trip link can watch that walk** while it runs (no login). The walker can end it and switch the link off at once.
- **Video positions are estimated** along the traced route (steady speed), not GPS.
- **Phones need https** for camera and GPS. Over plain http use the *simulated walk*.
- **Shared access codes**, public community reports (limited per device), one server process with SQLite.
- Not tested yet: real night videos, real Gemini, real Android/iPhone, the Docker image build, a real hosted deployment.

## Tests

```bash
cd ~/Projects/shadowmap/backend && .venv/bin/pytest      # 296 automated tests
cd ~/Projects/shadowmap/frontend && npm run build        # type-check + production build
```

Browser smoke test (no extra packages; uses the installed Chrome). Run it only against a **test copy** — it creates a simulated walk:

```
# terminal 1: a test copy of the database on port 8001
cd ~/Projects/shadowmap/backend && mkdir -p /tmp/sm-test/data && sqlite3 data/shadowmap.db ".backup '/tmp/sm-test/data/shadowmap.db'"
DATABASE_URL=sqlite:////tmp/sm-test/data/shadowmap.db DATA_DIR=/tmp/sm-test/data START_WORKERS=0 SENTINEL_TOKEN=smoke-code .venv/bin/uvicorn app.main:app --port 8001
# terminal 2: production build of the frontend on port 5174
cd ~/Projects/shadowmap/frontend && npx vite build --outDir /tmp/sm-test/dist && SM_API_TARGET=http://localhost:8001 npx vite preview --outDir /tmp/sm-test/dist --port 5174
# terminal 3
cd ~/Projects/shadowmap/frontend && SMOKE_BASE=http://localhost:5174 SMOKE_SENTINEL=smoke-code SMOKE_OUT=/tmp/sm-test/smoke node e2e/smoke.mjs
```
