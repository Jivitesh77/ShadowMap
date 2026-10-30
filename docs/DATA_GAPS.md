# Map data gaps around IIIT Guwahati

ShadowMap uses free OpenStreetMap (OSM) data. Around IIIT Guwahati that data is **incomplete**. This file records what is missing, measured from our saved download, so nobody presents the map as more complete than it is.

**ShadowMap does not claim Google-Maps-level accuracy or coverage.** Streets and places are only as good as OSM plus what our team verifies in person.

- Source file: `assets/demo-data/osm_2026-10-30.json` (OSM data as of 2026-10-30 05:55 UTC)
- Demo area: 26.0714–26.0894 N, 91.5505–91.5705 E (about 2 km × 2 km around the campus)
- Numbers below were measured on 2026-10-30 from the database built from that file.

## Roads

| What | Measured | What it means |
| --- | --- | --- |
| Street segments | 73 segments, 18.5 km, from 41 OSM roads | Only vehicle roads are mapped |
| Footpaths, lanes, steps, alleys | **0** | Short cuts people really walk are missing; routes may be longer than reality |
| Named segments | **6 of 73** (all NH17) | Most roads show as "Unnamed road"; briefings cannot name them |
| Streetlight information (`lit` tag) | **0 of 73** | Lighting is only known from Sentinel photos, never from the map |
| Roads touching the campus outline | 20 segments | Paths between campus buildings are probably not mapped (not verified on site) |
| Disconnected group | 5 segments (1.9 km) in the south-east corner | Join the rest only outside the downloaded area; routes to them fail with a clear message |

## Safe places

| What | Measured |
| --- | --- |
| Places inside the 2 km box | **6**, all shops / food (incl. the campus Canteen) |
| Police, hospital, pharmacy, petrol pump inside the box | **0** |
| Bus stops mapped inside the box | **0** (none in OSM; we have not checked on site) |
| Nearest police (OSM) | Azara Police Station, 6.7 km |
| Nearest hospital (OSM) | Azara 30 Bedded Rural Hospital (F.R.U), 7.5 km |
| Nearest pharmacy (OSM) | Baba Ganesh Medicos, 6.9 km |
| Nearest petrol pump (OSM) | Indian Oil, 5.5 km |
| Places with opening hours | **1 of 20** (South Indian Bank ATM, 24/7) |
| Places with a phone number | 5 of 20 |

Consequences: most places show **"Hours unknown"**; police and hospitals show **"Open (assumed)"** with a note; with map data alone every street scores yellow (45–64).

## Background map (OpenFreeMap)

The background picture comes from OpenFreeMap, which is also built from OSM but updated on its own schedule. It may show a road that ShadowMap's own data does not have (or the other way round). **Routes, scores and places always come from ShadowMap's own saved data**, never from the background picture. If the background map cannot load, ShadowMap still draws its streets, places and routes on a plain background.

## How gaps get filled

1. **Places checked in person** → `assets/demo-data/manual_places.json` (who checked, when, how), then `cd backend && .venv/bin/python -m scripts.build_map`. Shown on the map as "Manually added".
2. **Street conditions** (lighting, people, open shops) → Sentinel photos and community reports, not the map.
3. **Missing roads/footpaths** → optional: a team member adds them to openstreetmap.org (public, free), then re-download with `scripts.fetch_osm`. Must be done **before** night-ride data is collected, because rebuilding the map changes street ids.

Never fill a gap with a guess. Unknown stays labelled unknown.
