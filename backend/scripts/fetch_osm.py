"""Download the demo area's streets and safe places from OpenStreetMap ONCE and save them.

Run:  cd backend && .venv/bin/python -m scripts.fetch_osm
Saves assets/demo-data/osm_<date>.json. Never overwrites an existing file.
The demo itself never downloads map data; it reads the saved file via build_map.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEMO_DATA = Path(__file__).resolve().parents[2] / "assets" / "demo-data"
# Public Overpass servers (same OpenStreetMap data). Tried in order if one is busy.
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
USER_AGENT = "ShadowMap-student-prototype/0.1 (IIIT Guwahati showcase)"


def build_query(area: dict) -> str:
    b = area["bbox"]
    bbox = f"{b['south']},{b['west']},{b['north']},{b['east']}"
    lat, lon = area["center"]
    r = area["help_radius_m"]
    return f"""[out:json][timeout:120];
(
  way["highway"]({bbox});
)->.roads;
(
  nwr["amenity"]({bbox});
  nwr["shop"]({bbox});
  nwr["tourism"]({bbox});
  nwr["healthcare"]({bbox});
  nwr["emergency"]({bbox});
  node["highway"="bus_stop"]({bbox});
  nwr["public_transport"~"^(platform|station|stop_position)$"]({bbox});
  nwr["railway"~"^(station|halt)$"]({bbox});
  nwr["amenity"~"^(police|hospital|clinic|doctors|pharmacy|fuel|atm|bank|bus_station)$"](around:{r},{lat},{lon});
  nwr["healthcare"~"^(hospital|clinic|doctor|pharmacy|centre)$"](around:{r},{lat},{lon});
  nwr["shop"="chemist"](around:{r},{lat},{lon});
  nwr["shop"]["opening_hours"="24/7"](around:{r},{lat},{lon});
  nwr["railway"~"^(station|halt)$"](around:{r},{lat},{lon});
)->.places;
.roads out body geom;
.places out tags center meta;
"""


def main() -> int:
    area = json.loads((DEMO_DATA / "area.json").read_text())
    out = DEMO_DATA / f"osm_{datetime.now().strftime('%Y-%m-%dT%H%M')}.json"
    if out.exists():
        print(f"{out.name} already exists. Not downloading again (delete it yourself if you really want a fresh copy).")
        return 1
    query = build_query(area)
    data, used_url = None, None
    for attempt in range(3):
        for url in OVERPASS_URLS:
            print(f"Downloading from OpenStreetMap via {url} (attempt {attempt + 1})...")
            req = urllib.request.Request(
                url, data=urllib.parse.urlencode({"data": query}).encode(), headers={"User-Agent": USER_AGENT}
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as res:
                    data, used_url = json.load(res), url
                break
            except Exception as err:  # busy server, timeout, network
                print(f"  failed: {err}")
        if data:
            break
        time.sleep(20)
    if not data:
        print("All Overpass servers failed. Try again in a few minutes.")
        return 1
    data["shadowmap"] = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": used_url,
        "osm_data_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
        "area": area,
        "query": query,
        "licence": "OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0",
    }
    out.write_text(json.dumps(data, ensure_ascii=False))
    ways = sum(1 for e in data["elements"] if e["type"] == "way" and "geometry" in e)
    print(f"Saved {out} ({len(data['elements'])} elements, {ways} road ways)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
