# ShadowMap architecture (overview)

One frontend and one backend (see AGENTS.md §4 for the fixed technology choices).

```
Browser (React + Vite + Tailwind, Leaflet/OSM tiles)
  │  /api/*  (JSON; access codes and the walker token in headers, never in URLs)
  ▼
FastAPI app (backend/app, one process)
  ├─ routers/   map · route · walker (briefing, help point) · reports · walks (Walk With Me, trip page)
  │             dashboards (police, city) · sentinel (live photos, videos) · photos · google_places
  ├─ services/  scoring · routing (own Dijkstra) · street_state · places · hours · walks (rules, version-checked saves)
  │             video + video_jobs (FFmpeg) · redaction (YuNet + Haar) · photo_analysis + gemini · retention · storage
  ├─ middleware security headers → upload guard (video size / disk / access code) → CORS
  ├─ rate_limit.py   in-memory per-client limits (route, help point, walk start, briefing, reports, map, where-am-I)
  ├─ background threads (started with the app): walk clock (2 s, + cleanup every ~5 min), video queue, photo queue
  └─ SQLite (SQLAlchemy 2, WAL) in DATA_DIR + photo / video files in DATA_DIR
```

**Data flow.** Map data comes from saved OpenStreetMap downloads (`assets/demo-data/`, one folder per city) and is built
into the database by `scripts/build_map.py`. Scores combine road type, nearby places (open / closed / unknown at the walk
time), community reports and approved Sentinel photo analyses. Routes are planned on each city's own street graph.

**Walk With Me.** All safety rules run on the server: the walk clock asks "Are you safe?", escalates to contacts and the
(simulated) police dashboard, and keeps working when the phone goes quiet. Walk records carry a version number so the clock
and the walker's requests never overwrite each other.

**Sentinel.** Photos / video frames are blurred locally first; only blurred, approved copies are ever served. Without a
Gemini key nothing is analysed (photos stay private); without FFmpeg video mode answers 503.

**Cities.** Guwahati (default) and Delhi; streets, places, reports, video jobs, walks and police alerts are separated per
city (`services/cities.py`).

**Deployment (prepared, not done).** Backend on Render with a persistent disk, frontend on Vercel — docs/DEPLOYMENT.md.
Single process only (SQLite, in-memory limits, background threads).
