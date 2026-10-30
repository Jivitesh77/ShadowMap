"""Build the map tables (streets, places) from the saved OpenStreetMap file + manually verified places.

Run:  cd backend && .venv/bin/python -m scripts.build_map
Reads the newest assets/demo-data/osm_*.json and assets/demo-data/manual_places.json.
No internet needed. Refuses to run once observations or reports exist, because they point at street ids.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.db import engine, init_db
from app.services.geo import haversine_m, line_length_m
from app.services.osm import CATEGORIES, WALKABLE, place_category, road_class

DEMO_DATA = Path(__file__).resolve().parents[2] / "assets" / "demo-data"


def latest_osm_file() -> Path:
    files = sorted(DEMO_DATA.glob("osm_*.json"))
    if not files:
        sys.exit("No osm_*.json in assets/demo-data. Run: .venv/bin/python -m scripts.fetch_osm")
    return files[-1]


def in_bbox(lat: float, lon: float, b: dict) -> bool:
    return b["south"] <= lat <= b["north"] and b["west"] <= lon <= b["east"]


def split_ways(ways: list[dict]) -> list[dict]:
    """Cut each road at junctions, so every street segment runs between two junctions (graph edges)."""
    use = Counter()
    for w in ways:
        for i, n in enumerate(w["nodes"]):
            use[n] += 2 if i in (0, len(w["nodes"]) - 1) else 1
    segments = []
    for w in ways:
        nodes, geom = w["nodes"], [[p["lat"], p["lon"]] for p in w["geometry"]]
        start = 0
        for i in range(1, len(nodes)):
            if i == len(nodes) - 1 or use[nodes[i]] > 1:
                segments.append({"way": w, "start_node": nodes[start], "end_node": nodes[i], "geometry": geom[start : i + 1]})
                start = i
    return segments


def build_streets(elements: list[dict], bbox: dict) -> list[models.Street]:
    ways = [
        e for e in elements
        if e["type"] == "way" and "geometry" in e and e.get("tags", {}).get("highway") in WALKABLE
        and e["tags"].get("access") not in ("private", "no") and e["tags"].get("foot") != "no"
    ]
    streets = []
    for seg in split_ways(ways):
        geom = seg["geometry"]
        inside = any(in_bbox(lat, lon, bbox) for lat, lon in geom)
        if not inside:
            continue  # parts of long roads that run far outside the demo area
        tags = seg["way"]["tags"]
        streets.append(models.Street(
            osm_way_id=seg["way"]["id"],
            name=tags.get("name") or tags.get("ref"),
            road_type=tags["highway"],
            road_class=road_class(tags),
            lit=tags.get("lit"),
            start_node=seg["start_node"],
            end_node=seg["end_node"],
            length_m=round(line_length_m(geom), 1),
            geometry=[[round(a, 7), round(b, 7)] for a, b in geom],
            in_demo_area=True,
        ))
    return streets


def build_osm_places(elements: list[dict], bbox: dict) -> list[models.Place]:
    places, seen = [], set()
    for e in elements:
        tags = e.get("tags", {})
        if "geometry" in e or not tags:
            continue  # roads
        cat = place_category(tags)
        if not cat:
            continue
        lat, lon = (e["lat"], e["lon"]) if e["type"] == "node" else (e["center"]["lat"], e["center"]["lon"])
        osm_id = f"{e['type']}/{e['id']}"
        if osm_id in seen:
            continue
        seen.add(osm_id)
        places.append(models.Place(
            osm_id=osm_id,
            name=tags.get("name") or tags.get("brand") or tags.get("operator"),
            category=cat,
            lat=lat,
            lon=lon,
            opening_hours=tags.get("opening_hours"),
            phone=tags.get("phone") or tags.get("contact:phone"),
            source="openstreetmap",
            in_demo_area=in_bbox(lat, lon, bbox),
        ))
    return places


def build_manual_places(bbox: dict) -> list[models.Place]:
    path = DEMO_DATA / "manual_places.json"
    if not path.exists():
        return []
    places = []
    for i, p in enumerate(json.loads(path.read_text()).get("places", []), start=1):
        missing = [k for k in ("name", "category", "lat", "lon", "verified_by", "verified_on") if not p.get(k)]
        if missing:
            sys.exit(f"manual_places.json entry {i} is missing {missing}. Every manual place must say who verified it and when.")
        if p["category"] not in CATEGORIES:
            sys.exit(f"manual_places.json entry {i}: category must be one of {CATEGORIES}")
        places.append(models.Place(
            osm_id=None,
            name=p["name"],
            category=p["category"],
            lat=float(p["lat"]),
            lon=float(p["lon"]),
            opening_hours=p.get("opening_hours"),
            phone=p.get("phone"),
            source="manual",
            in_demo_area=in_bbox(float(p["lat"]), float(p["lon"]), bbox),
            verified_by=p["verified_by"],
            verified_on=p["verified_on"],
            note=p.get("note"),
        ))
    return places


def main() -> int:
    src = latest_osm_file()
    data = json.loads(src.read_text())
    area = data["shadowmap"]["area"]
    bbox = area["bbox"]

    streets = build_streets(data["elements"], bbox)
    osm_places = build_osm_places(data["elements"], bbox)
    manual_places = build_manual_places(bbox)

    init_db()
    with Session(engine, expire_on_commit=False) as db:
        used = db.scalar(select(func.count()).select_from(models.Observation)) + db.scalar(
            select(func.count()).select_from(models.Report)
        )
        if used:
            sys.exit("Observations or reports already exist and point at current street ids. Not rebuilding the map.")
        # Map tables only hold data re-created from the saved files above, so they are rebuilt from scratch.
        models.Street.__table__.drop(db.connection(), checkfirst=True)
        models.Place.__table__.drop(db.connection(), checkfirst=True)
        models.Street.__table__.create(db.connection())
        models.Place.__table__.create(db.connection())
        db.add_all(streets + osm_places + manual_places)
        db.commit()

    lat0, lon0 = area["center"]
    print(f"Built map from {src.name} (OSM data as of {data['shadowmap'].get('osm_data_timestamp')})")
    print(f"Street segments: {len(streets)}  total length {sum(s.length_m for s in streets) / 1000:.1f} km")
    print("  by class:", dict(Counter(s.road_class for s in streets)))
    print("  by OSM type:", dict(Counter(s.road_type for s in streets)))
    print(f"Places from OpenStreetMap: {len(osm_places)}   manually verified: {len(manual_places)}")
    for inside in (True, False):
        group = [p for p in osm_places + manual_places if p.in_demo_area == inside]
        print(f"  {'inside demo area' if inside else 'nearby help outside area'}: {dict(Counter(p.category for p in group))}")
    print(f"  with opening hours listed: {sum(1 for p in osm_places + manual_places if p.opening_hours)}")
    nearest = {}
    for p in osm_places + manual_places:
        d = haversine_m(lat0, lon0, p.lat, p.lon)
        if p.category in ("police", "hospital", "fuel", "pharmacy") and d < nearest.get(p.category, (1e12,))[0]:
            nearest[p.category] = (d, p.name)
    for cat, (d, name) in sorted(nearest.items()):
        print(f"  nearest {cat}: {name or '(no name)'} — {d / 1000:.1f} km from campus centre")
    return 0


if __name__ == "__main__":
    sys.exit(main())
