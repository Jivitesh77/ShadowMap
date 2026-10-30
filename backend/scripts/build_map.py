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
from app.services.places import Candidate, best_match, kinds_conflict, same_name

DEMO_DATA = Path(__file__).resolve().parents[2] / "assets" / "demo-data"


def latest_osm_file() -> Path:
    files = sorted(DEMO_DATA.glob("osm_*.json"))
    if not files:
        sys.exit("No osm_*.json in assets/demo-data. Run: .venv/bin/python -m scripts.fetch_osm")
    return files[-1]


def in_bbox(lat: float, lon: float, b: dict, pad: float = 0.0) -> bool:
    return b["south"] - pad <= lat <= b["north"] + pad and b["west"] - pad <= lon <= b["east"] + pad


# Road pieces up to ~300 m outside the box are kept, so roads that leave the box and come back stay connected.
ROUTING_PAD_DEG = 0.003


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
        if not any(in_bbox(lat, lon, bbox, ROUTING_PAD_DEG) for lat, lon in geom):
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
            in_demo_area=any(in_bbox(lat, lon, bbox) for lat, lon in geom),
        ))
    return streets


def _richness(tags: dict) -> int:
    return len(tags) + (5 if tags.get("name") else 0)


def build_osm_places(elements: list[dict], bbox: dict) -> list[models.Place]:
    """OSM places, with OSM's own duplicates merged (e.g. a hospital mapped as both a point and a building)."""
    raw = []
    seen = set()
    for e in elements:
        tags = e.get("tags", {})
        if "geometry" in e or not tags:
            continue  # roads
        cat = place_category(tags)
        if not cat:
            continue
        osm_id = f"{e['type']}/{e['id']}"
        if osm_id in seen:
            continue
        seen.add(osm_id)
        lat, lon = (e["lat"], e["lon"]) if e["type"] == "node" else (e["center"]["lat"], e["center"]["lon"])
        raw.append((e, tags, cat, osm_id, lat, lon))
    raw.sort(key=lambda r: -_richness(r[1]))  # keep the most detailed entry when OSM has duplicates

    places: list[models.Place] = []
    kept: list[Candidate] = []
    for e, tags, cat, osm_id, lat, lon in raw:
        name = tags.get("name") or tags.get("brand") or tags.get("operator")
        cand = Candidate(osm_id, name, cat, lat, lon)
        dup = best_match(cand, kept, taken=set())
        if dup and name and dup[0].name and same_name(name, dup[0].name) and not kinds_conflict(name, dup[0].name):
            target = next(pl for pl in places if pl.osm_id == dup[0].key)
            target.duplicate_osm_ids = [*(target.duplicate_osm_ids or []), osm_id]
            continue
        kept.append(cand)
        places.append(models.Place(
            osm_id=osm_id,
            name=name,
            category=cat,
            lat=lat,
            lon=lon,
            opening_hours=tags.get("opening_hours"),
            hours_source="osm" if tags.get("opening_hours") else None,
            phone=tags.get("phone") or tags.get("contact:phone"),
            sources=["osm"],
            osm_last_edited=e.get("timestamp"),
            in_demo_area=in_bbox(lat, lon, bbox),
        ))
    return places


def load_verified_places(bbox: dict) -> list[dict]:
    """Places the ShadowMap team checked in person (assets/demo-data/manual_places.json)."""
    path = DEMO_DATA / "manual_places.json"
    if not path.exists():
        return []
    out = []
    for i, p in enumerate(json.loads(path.read_text()).get("places", []), start=1):
        missing = [k for k in ("name", "category", "lat", "lon", "verified_by", "verified_on") if not p.get(k)]
        if missing:
            sys.exit(f"manual_places.json entry {i} is missing {missing}. Every verified place must say who checked it and when.")
        if p["category"] not in CATEGORIES:
            sys.exit(f"manual_places.json entry {i}: category must be one of {CATEGORIES}")
        out.append({**p, "lat": float(p["lat"]), "lon": float(p["lon"]), "in_demo_area": in_bbox(float(p["lat"]), float(p["lon"]), bbox)})
    return out


def merge_verified(osm_places: list[models.Place], verified: list[dict]) -> tuple[list[models.Place], list[str]]:
    """Attach each team-verified place to the OSM entry for the same real place, or add it as a new place.
    Team data wins for name, position, hours and phone (it was checked on site); OSM keeps its id and edit date."""
    pool = [Candidate(pl.osm_id, pl.name, pl.category, pl.lat, pl.lon) for pl in osm_places]
    by_id = {pl.osm_id: pl for pl in osm_places}
    taken: set[str] = set()
    added: list[models.Place] = []
    log: list[str] = []
    for v in verified:
        target, reason = None, None
        if v.get("osm_id"):
            target = by_id.get(v["osm_id"])
            if not target:
                sys.exit(f"manual_places.json: {v['name']} points to {v['osm_id']}, which is not in the OSM download.")
            reason = "linked by the team to this OpenStreetMap entry"
        else:
            m = best_match(Candidate("verified", v["name"], v["category"], v["lat"], v["lon"]), pool, taken)
            if m:
                target, reason = by_id[m[0].key], m[1]
        common = dict(name=v["name"], category=v["category"], lat=v["lat"], lon=v["lon"], verified_by=v["verified_by"],
                      verified_on=v["verified_on"], note=v.get("note"), in_demo_area=v["in_demo_area"])
        if target:
            taken.add(target.osm_id)
            for k, val in common.items():
                setattr(target, k, val)
            if v.get("opening_hours"):
                target.opening_hours, target.hours_source = v["opening_hours"], "shadowmap"
            if v.get("phone"):
                target.phone = v["phone"]
            target.sources = ["osm", "shadowmap"]
            target.match_note = reason
            log.append(f"{v['name']}: same place as OSM {target.osm_id} ({reason})")
        else:
            added.append(models.Place(osm_id=None, opening_hours=v.get("opening_hours"),
                                      hours_source="shadowmap" if v.get("opening_hours") else None,
                                      phone=v.get("phone"), sources=["shadowmap"], **common))
            log.append(f"{v['name']}: new place (no matching OSM entry)")
    return osm_places + added, log


def main() -> int:
    src = latest_osm_file()
    data = json.loads(src.read_text())
    area = data["shadowmap"]["area"]
    bbox = area["bbox"]

    streets = build_streets(data["elements"], bbox)
    osm_places = build_osm_places(data["elements"], bbox)
    all_places, merge_log = merge_verified(osm_places, load_verified_places(bbox))

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
        db.add_all(streets + all_places)
        db.commit()

    lat0, lon0 = area["center"]
    print(f"Built map from {src.name} (OSM data as of {data['shadowmap'].get('osm_data_timestamp')})")
    print(f"Street segments: {len(streets)}  total length {sum(s.length_m for s in streets) / 1000:.1f} km")
    print("  by class:", dict(Counter(s.road_class for s in streets)))
    print("  by OSM type:", dict(Counter(s.road_type for s in streets)))
    dups = sum(len(p.duplicate_osm_ids or []) for p in all_places)
    print(f"Places: {len(all_places)}  by source: {dict(Counter('+'.join(p.sources) for p in all_places))}  (OSM duplicates merged: {dups})")
    for line in merge_log:
        print("  verified:", line)
    for inside in (True, False):
        group = [p for p in all_places if p.in_demo_area == inside]
        print(f"  {'inside demo area' if inside else 'nearby help outside area'}: {dict(Counter(p.category for p in group))}")
    print(f"  with opening hours listed: {sum(1 for p in all_places if p.opening_hours)}")
    nearest = {}
    for p in all_places:
        d = haversine_m(lat0, lon0, p.lat, p.lon)
        if p.category in ("police", "hospital", "fuel", "pharmacy") and d < nearest.get(p.category, (1e12,))[0]:
            nearest[p.category] = (d, p.name)
    for cat, (d, name) in sorted(nearest.items()):
        print(f"  nearest {cat}: {name or '(no name)'} — {d / 1000:.1f} km from campus centre")
    return 0


if __name__ == "__main__":
    sys.exit(main())
