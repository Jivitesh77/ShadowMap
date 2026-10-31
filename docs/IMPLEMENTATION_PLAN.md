> **Historical document** — describes the original build plan. Current status: docs/SPRINT_STATUS.md and docs/KNOWN_ISSUES.md.

# ShadowMap — Implementation Plan

Budget: **36 hours of building**, then **12 hours of testing**.
Each milestone is small, can be checked on its own, and has a **Done-when check** that must actually be run before it is marked done.
Hours are estimates. If we fall behind, use the **cut list** at the bottom — never skip a Done-when check.

Priority tiers:
- **P1 – Must have** for the demo story (§16 of the blueprint). Built first.
- **P2 – Should have.** Built after all P1 items pass.
- **P3 – Nice to have.** Only if time remains.

---

## Architecture in one picture

```
 Phones / laptop browser                      Laptop (backend)                       Outside services
 ┌──────────────────────────┐   HTTP + WS    ┌──────────────────────────────┐        ┌───────────────────┐
 │ ONE React app (Vite)     │ ─────────────► │ ONE FastAPI server (Python)  │ ─────► │ Google Gemini     │
 │  /           Walker      │ ◄───────────── │  routing (Dijkstra)          │        │ (photo + briefing)│
 │  /sentinel   Sentinel    │   live updates │  safety score                │        └───────────────────┘
 │  /trip/:id   Contact     │                │  walks + alert escalation    │
 │  /police     Police      │                │  blur + 6 h photo deletion   │ ◄───── OpenStreetMap data
 │  /city       City        │                │  FFmpeg frame extraction     │        (downloaded once
 └──────────────────────────┘                │  SQLite database             │         into assets/demo-data)
        ▲ map tiles from OpenStreetMap       └──────────────────────────────┘
```

Plain-language summary: the **frontend** is the set of screens people see in a browser. The **backend** is the program on the laptop that does all the thinking and stores data. Only the backend knows the Gemini key and talks to Gemini.

### Key simplifications (chosen to fit 36 hours)

| Decision | Why |
| --- | --- |
| Map data downloaded **once** from OpenStreetMap's Overpass service into `assets/demo-data/`, then converted into SQLite | Real data, no live dependency during the demo, no heavy mapping library |
| Our own small graph builder instead of osmnx | osmnx brings many heavy dependencies; we only need streets split at junctions |
| Our own opening-hours reader for common formats (`24/7`, `Mo-Su 08:00-23:00`, `Mo-Fr ...; Sa ...`) | Anything it cannot read is shown honestly as "hours unknown" |
| One WebSocket channel `/ws` that broadcasts small "something changed" messages | Screens then re-fetch data; simple and reliable |
| Photos analysed in a background queue inside the FastAPI process (no Celery/Redis) | One process, one server |
| Demo clock: the backend can pretend it is 11:30 pm | Needed to demo "open now" in daytime; always labelled "DEMO CLOCK" on screen |
| Demo timers: shortened walk timers when `DEMO_MODE=true` | Matches blueprint §9 "in the prototype" |
| For phones: build the frontend and serve it from FastAPI, reached over https via a tunnel or hosting | Phones only allow camera/GPS on https. **Exact method chosen with the owner at M12; nothing is published without approval** |

---

## Milestones

### M0 — Project skeleton (P1, ~2 h)
- Create `backend/` with a Python virtual environment (a private box of Python packages for this project), `requirements.txt`, `app/main.py` with `GET /api/health`.
- Create `frontend/` with Vite + React + TypeScript + Tailwind + Leaflet. Show a full-screen map and a small "Backend: connected / not connected" badge.
- Add `backend/.env.example` listing the settings (no real values).
- **Done when:** `pytest` runs (one health test passes) and the browser at http://localhost:5173 shows the OSM map plus "Backend: connected".

### M1 — Real map data for the demo area (P1, ~3 h)
- Confirm the demo area box with the owner (about 2 km × 2 km around IIIT Guwahati; exact centre taken from OpenStreetMap, not guessed).
- `scripts/fetch_osm.py`: download streets and safe places (police, hospital, pharmacy, fuel, ATM, bus stop/station, hotel, 24 h shops/food) from Overpass; save raw file to `assets/demo-data/osm_<date>.json` (kept as evidence).
- `scripts/build_graph.py`: split ways into street segments at junctions, compute lengths, store `streets`, `nodes`, `places` in SQLite.
- `GET /api/map` returns streets (as lines) and places.
- **Done when:** the script prints counts of streets and of each place category; the map draws the streets and the places; a manual check against openstreetmap.org shows the same police stations/hospitals/pharmacies/fuel stations. Gaps go in KNOWN_ISSUES (not filled with invented data).

### M2 — "Open now" and the demo clock (P1, ~2 h)
- Opening-hours reader with unit tests (24/7, ranges, multiple day groups, closing after midnight, unknown).
- Category defaults from blueprint §4 (police/hospital/hotel = 24 h; others = unknown if missing).
- `GET /api/map?at=23:30` and a time picker on the map; open = bright icon, closed = grey, unknown = outlined.
- "Open now only" filter.
- **Done when:** tests pass, and at 23:30 each place shows the status that its OSM hours imply (spot-check 5 places by hand).

### M3 — Map score and street colours (P1, ~1.5 h)
- Map score from blueprint §7 (road type points, +5 per open safe place within 50 m up to +15, +10 for police/hospital within 200 m).
- Colour streets green/yellow/red; tap a street to see score and "map data only".
- **Done when:** unit tests for the score pass, and the map shows all three colours where the data supports them.

### M4 — Route finder: shortest vs safest (P1, ~3 h)
- Dijkstra in Python on the street graph; cost = length for shortest, `length × (1 + 3 × (100−S)/100)` for safest.
- Detour limit 1.5 × shortest; if exceeded, say so plainly.
- `POST /api/route` returns both routes + comparison (distance, walking time at ~5 km/h, metres on red streets, safe places passed, freshest observation).
- Walker page: tap start + destination (or pick from a list of named campus points from OSM), draw both routes, comparison card.
- **Done when:** routing tests pass on a tiny hand-made graph; for the chosen demo walk the two routes are drawn and the comparison numbers are shown. (If the two routes are identical with map data alone, note it — Sentinel data in M6 is what makes them differ.)

### M5 — Sentinel capture page (P1, ~3 h)
- `/sentinel` page: choose Sentinel label ("Zomato Rider #01"), start/stop switch, camera preview, photo every N seconds (5–10, default 7), shrink to 640 px, send with GPS, accuracy, heading, speed, time.
- Rules: only while moving > 5 km/h, skip if < 30 m from last photo (both can be turned off for testing while walking).
- `POST /api/sentinel/photo`: snap to nearest street within 25 m, reject poor GPS accuracy, store photo with 6 h delete time.
- **Done when:** on a laptop (localhost allows the camera), and later on a phone over https, a test session stores rows in `observations` linked to the correct street.

### M6 — AI street analysis, live colours, blur, deletion (P1, ~4 h)
- Gemini call with a fixed JSON format (blueprint §6 fields + "unclear"); describe-places-not-people rule in the prompt; unclear photos dropped.
- Photo score + freshness weighting → updated street score; WebSocket broadcast so every open map recolours.
- Faces/plates blurred with OpenCV before any photo is served; background job deletes photos past their delete time every 5 min (AI text kept).
- Tap street → latest blurred photo, AI note, "seen N min ago by Rapido #02", strip of recent photos.
- Queue + retry for Gemini rate limits.
- **Done when:** sending a real dark-street photo turns that street red on a second open browser within seconds; a photo with a face is shown blurred; an observation with an expired delete time loses its photo file but keeps its text.

### M7 — Video mode (P1 backup, ~2.5 h)
- Upload a video file + trace the path by clicking points on the map + Sentinel label.
- FFmpeg extracts one frame every 5 s; frames placed along the traced path in proportion to time; each frame goes through the same pipeline as M5/M6.
- **Done when:** a real night video from `assets/videos/` colours the streets along its traced path.

### M8 — AI route briefing + voice (P1, ~2 h)
- `POST /api/route/briefing`: send Gemini only facts (segments, notes with ages, safe places along route, walk time). 4–6 sentences, English or Hindi. Rules from §8 in the prompt.
- Check the answer: reject/retry if it names a place not in the facts list.
- Read aloud with the browser voice; text always shown on screen.
- **Done when:** for the demo route the briefing mentions only places and times present in the data (checked line by line) and is spoken in English; Hindi tested on at least one device.

### M9 — Community reports + nearest safe spot (P1, ~2 h)
- Report buttons (no free text): broken light, dark, deserted, felt unsafe, well lit, place closed/open. Effects and fade times from §10; agreement bonus; per-device rate limit.
- `GET /api/safe-spot`: nearest place open at the walk time, routed preferring green streets; draw route + walking time.
- **Done when:** a report sent from a second browser changes that street's score and the safest route changes accordingly; "Nearest safe spot" draws a route to an open place.

### M10 — Walk With Me + escalation + help bar (P1, ~5 h)
- Start walk: up to 3 contacts (name + phone, stored locally), 4-digit PIN and duress PIN, trip link `/trip/<id>`.
- Phone sends position every few seconds; backend checks triggers (stopped, off-route, late, SOS).
- Ladder: "Are you safe?" (60 s, PIN) → contact alert on trip page → police alert after 2 more min. SOS jumps to police. Duress PIN looks like cancel but escalates silently.
- Help bar: 112 (press-and-hold), 181, nearest police station (from OSM phone tag, else 100), call contact, fake call. **In DEMO_MODE all calls dial the team member's number.** "Where am I" card.
- Contact page: live dot, route, ETA, alerts, "reached safely".
- Police page: alerts newest first, live position, route, last photo, phone; status Acknowledged → Unit sent → Resolved.
- **Done when:** on two browsers (walker + contact) and the police page, standing still leads to "Are you safe?", then a contact alert, then a police alert; correct PIN cancels; duress PIN escalates; arrival sends "reached safely".

### M11 — City dashboard + repair list (P2, ~1.5 h)
- Dark-street hotspots, broken-light reports ranked by number of routes through the street, photo evidence, nights dark, CSV export.
- Sentinel coverage view (streets seen in the last hour) on the police page.
- **Done when:** reported broken lights appear ranked with photos and the CSV opens in a spreadsheet program.

### M12 — Phone access, demo reset, README (P1, ~2.5 h)
- Choose with the owner how phones reach the app over https (options in KNOWN_ISSUES #4). **Ask before publishing anything.**
- `scripts/reset_demo.py`: restore the saved night-ride observations so the map is coloured at demo start (only real recorded data).
- README with plain-language run steps; QR code target URL for judges' reports.
- **Done when:** a phone opens the Walker page over https, camera + GPS work on the Sentinel page, and reset_demo restores a coloured map.

### Buffer (~2 h)
Unexpected problems. If unused, spend on P3.

**Total ≈ 34 h + 2 h buffer = 36 h.**

---

## P3 — only if time remains
- Re-route during a walk when a fresher photo shows a problem ahead, with a spoken reason.
- Spoken turn-by-turn hints.
- "Before and after" view on the city dashboard.
- Battery-low notice to contacts.

## Cut list (use in this order if behind schedule)
1. P3 items.
2. Hindi briefing (keep English).
3. Number-plate blur (keep face blur), record in KNOWN_ISSUES.
4. Fake call button.
5. Agreement bonus and rate limits on reports (keep basic report effects).
6. City dashboard CSV export (keep the on-screen list).

## Testing phase (12 h, after building)
1. Automated: `pytest` all green (score, hours, routing, walk ladder timers).
2. Full demo script (blueprint §16) on laptop + 2 phones, twice in a row.
3. Android and iPhone: camera, GPS, voice, call buttons (DEMO_MODE).
4. Offline drill: Gemini key removed → map, routing and alerts still work with pre-analysed data.
5. Hotspot drill: whole demo over a phone hotspot.
6. Every known issue reviewed: fixed, worked around, or written into the demo script.
