# Map data gaps around IIIT Guwahati

ShadowMap uses free OpenStreetMap (OSM) data. Around IIIT Guwahati that data is **incomplete**. This file records what is missing, measured from our saved download, so nobody presents the map as more complete than it is.

**ShadowMap does not claim Google-Maps-level accuracy or coverage.** Streets and places are only as good as OSM plus what our team verifies in person.

- Source file: `assets/demo-data/osm_2026-10-30T1233.json` (OSM data as of 2026-10-30 07:02 UTC; wider place search). The first download `osm_2026-10-30.json` is kept.
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

## Places (help points and open places)

| What | Measured |
| --- | --- |
| Places found (box + 8 km help ring) | **27**: 6 inside the box (all shops / food, incl. the campus Canteen), 21 outside (8 clinics, 6 ATMs, 2 petrol pumps, 2 railway stations, 1 hospital, 1 police, 1 pharmacy) |
| Police, hospital, pharmacy, petrol pump inside the box | **0** |
| Bus stops mapped inside the box | **0** (none in OSM; we have not checked on site) |
| Nearest police (OSM) | Azara Police Station, 6.7 km |
| Nearest hospital (OSM) | Azara 30 Bedded Rural Hospital (F.R.U), 7.5 km |
| Nearest pharmacy (OSM) | Baba Ganesh Medicos, 6.9 km |
| Nearest petrol pump (OSM) | Indian Oil, 5.5 km |
| Places with opening hours | **1 of 27** (South Indian Bank ATM, 24/7) |
| Team-verified (ShadowMap) places | 0 so far |

Consequences: 26 of 27 places show **"Hours unknown"** — including police and hospitals, which are never assumed open; every OSM-only place has confidence "medium" at best; with map data alone every street scores yellow (45–64).

## Background map tiles

The Leaflet map shows OpenStreetMap's standard tiles. They may be newer than our 2026-10-30 download, so a road can appear in the picture but not be routable. **Routes, scores and places always come from ShadowMap's own saved data.** Without internet the tiles are blank, but ShadowMap's streets, places and routes are still drawn.

## Google Places (optional)

If a Google key is configured, the Walker panel can list extra nearby places from Google Maps. These are **not** used to fill the gaps above: they are not drawn on our map, not saved, and not merged (Google's terms). A team member may visit a place found there and then add it as a ShadowMap-verified place from their own on-site check.

## How gaps get filled

1. **Places checked in person** → `assets/demo-data/manual_places.json` (who checked, when, how), then `cd backend && .venv/bin/python -m scripts.build_map`. Shown on the map with a white ring and labelled "ShadowMap verified".
2. **Street conditions** (lighting, people, open shops) → Sentinel photos and community reports, not the map.
3. **Missing roads/footpaths** → optional: a team member adds them to openstreetmap.org (public, free), then re-download with `scripts.fetch_osm`. Must be done **before** night-ride data is collected, because rebuilding the map changes street ids.

Never fill a gap with a guess. Unknown stays labelled unknown.

---

# Second demo city: Aastha Kunj, Delhi (added 2026-10-30)

**Boundary.** Centre: Aastha Kunj Park, OpenStreetMap way 479658972 (28.5547447, 77.2574976), looked up via Nominatim.
Box: south 28.5367, west 77.2370, north 28.5727, east 77.2780 — about 4 km × 4 km (≈2 km each way from the park).
Help places (police, hospital, clinic, pharmacy, petrol pump, ATM, transit) are also loaded up to 4 km from the centre.
Landmarks inside the box (positions from OpenStreetMap/Nominatim, not guessed): Lotus Temple 0.2 km, Sri Sri Radha Parthasarathi Mandir (ISKCON) 0.4 km,
Kalkaji Mandir 0.6 km, Nehru Place 0.7 km and its metro station 0.8 km, East of Kailash ~0.8 km, Kalkaji ~1.4 km.
Two wrong Nominatim matches were rejected: "ISKCON Delhi" (returned Dwarka, 23 km away) and "Nehru Place, New Delhi" (returned central Delhi).

**Source and attribution.** OpenStreetMap via the Overpass API, downloaded once on 2026-10-30 (OSM data as of 2026-10-30 11:46 UTC),
saved as `assets/demo-data/delhi/osm_2026-10-30T1716.json` (6,375 elements, 3,993 road ways). © OpenStreetMap contributors, ODbL.
No Google data is stored or merged. `assets/demo-data/delhi/manual_places.json` is empty: the team has checked no Delhi place in person.

**Streets.** 6,272 street pieces, 394 km (main 1,347 · residential 2,921 · lanes/footways/paths 1,932 · underpasses 72).
95.5 % of the length (376 km) forms one connected network. The other 4.5 % are short isolated pieces: park footways, building corridors, private driveways.
If a tapped point is nearest to such a piece, the route uses the nearest connected street within 100 m and says so in the route notes.
Only 32 % of the length has a street name, and only 61 pieces carry a `lit` tag, so most lighting is unknown until Sentinel photos exist.

**Places (all "OSM-listed", none team-verified).** 1,442 places: 1,204 inside the box and 238 nearby help places outside it.

| Category | Inside box | Nearby (≤4 km) | With opening hours | Unnamed |
| --- | --- | --- | --- | --- |
| Shops & food | 873 | 4 | 64 | 71 |
| Transit stops | 99 | 20 | 1 | 21 |
| ATMs | 91 | 68 | 47 | 6 |
| Hotels | 43 | 0 | 3 | 3 |
| Hospitals | 26 | 34 | 1 | 3 |
| Pharmacies | 25 | 26 | 4 | 8 |
| Clinics | 22 | 37 | 9 | 2 |
| Petrol pumps | 16 | 33 | 8 | 2 |
| Police | 9 | 16 | 2 | 8 |

Verification, using the existing ShadowMap fields: every Delhi place has source `osm`.
- Named entries show "Listed on OpenStreetMap; not checked by the ShadowMap team" (confidence medium).
- The 124 unnamed entries show confidence low (needs review).
- Independently verified: 0.

Only 139 places list opening hours, so at night most places show **Hours unknown**. They are never assumed open.

**Scores without photos.** Every Delhi street currently has a map-only baseline score (road type, `lit` tag, nearby places that are not closed).
At 11:30 pm many footways and lanes are red, because nothing nearby is known to be open. This is the honest result of missing data, not a judgement about Delhi.

**Known gaps.**
- OSM inside private colonies and parks may be incomplete; gates and their closing times are not mapped.
- The metro station is mapped, but its entrances and opening times are not used for routing.
- Shops' hours change often; OSM hours may be out of date.
- There is no Sentinel footage of Delhi yet.
