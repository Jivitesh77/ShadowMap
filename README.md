# ShadowMap

A live map of how safe each street is at night, for IIIT Guwahati and the surrounding area.
It routes people along the safest path, explains the route in plain words, and watches over them until they arrive.

Full specification: [BLUEPRINT.md](BLUEPRINT.md) · Build plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) · Progress: [docs/SPRINT_STATUS.md](docs/SPRINT_STATUS.md)

## Start the app

One command starts everything (backend server + frontend screens):

```bash
cd ~/Projects/shadowmap
./start.sh
```

Then open **http://localhost:5173** in your browser (works on this laptop only).
Press `Ctrl + C` once in that terminal to stop everything.

The **Sentinel** page asks for an access code. It is in `backend/.env`; show it with `grep SENTINEL_TOKEN ~/Projects/shadowmap/backend/.env`.
To test Live mode in daytime or on foot, set `SENTINEL_ENFORCE_NIGHT=false` / `SENTINEL_ENFORCE_MOVING=false` in `backend/.env` and restart (set back to `true` afterwards).

Notes:
- `http://localhost:8000` is the backend. It has no screens; it only answers the app's data requests.
- If you see "Port ... is already in use", ShadowMap is already running in another terminal — use that one, or stop it there first.

## First-time setup (already done on the tech lead's laptop)

```bash
cd ~/Projects/shadowmap/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

cd ~/Projects/shadowmap/frontend
npm install
```

## Map data

The map uses real OpenStreetMap data, downloaded once and saved in `assets/demo-data/`. The demo never downloads it again.

- Add a place the team checked in person: edit `assets/demo-data/manual_places.json` (instructions are inside), then rebuild:
  ```bash
  cd ~/Projects/shadowmap/backend && .venv/bin/python -m scripts.build_map
  ```
- Download fresh OpenStreetMap data (rarely needed, needs internet): `.venv/bin/python -m scripts.fetch_osm`, then `build_map`.

## Map and places

- Map: Leaflet with OpenStreetMap tiles. Other tile server: copy `frontend/.env.example` to `frontend/.env` and set `VITE_TILE_URL`.
- Places: OpenStreetMap + places the team checked in person (`assets/demo-data/manual_places.json`). Known gaps: [docs/DATA_GAPS.md](docs/DATA_GAPS.md).
- Optional Google Places search: put a Google Places API (New) key in `backend/.env` as `GOOGLE_PLACES_API_KEY=...` (never in the frontend, never in chat). Results appear only in a separate "More places nearby — Google Maps" list, never on the map, and are not saved. Searches cost money beyond Google's free usage; set a budget alert in Google Cloud. Without a key the app works normally.

## Walker (main screen)

Set **A** (start) and **B** (destination) by tapping the map, **My location**, or **Choose a place**. Pick the walk time. ShadowMap shows the shortest and the safest route, a comparison, and a briefing you can hear in English or Hindi (AI-written once a Gemini key is set, otherwise a labelled summary from the data). The **Report** tab sends one-tap street reports; **Help point** finds the nearest place known to be open and draws the walk there.

## Sentinel videos

Copy night-ride videos into `assets/videos/` (they are only read, never changed). Open **Sentinel → Video mode**, pick the video, tap the ride's route on the map, enter when it was recorded, and press **Process video**. Frames are taken every 5 seconds in the background and placed along the traced route (not GPS). They wait for AI analysis until a Gemini key is set.

## Run the tests

```bash
cd ~/Projects/shadowmap/backend && .venv/bin/pytest
cd ~/Projects/shadowmap/frontend && npm run build
```

## Secrets

Keys go only in `backend/.env`, which is never saved to git. Never put keys in the frontend, in docs, or in chat.
