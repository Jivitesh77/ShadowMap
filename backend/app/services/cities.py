"""Demo cities (assets/demo-data/cities.json). Each city has its own folder with area.json, osm_*.json and
manual_places.json, its own streets/places in the database (column `city`), and its own routing graph."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

DEMO_DATA = Path(__file__).resolve().parents[3] / "assets" / "demo-data"


@lru_cache
def registry() -> dict:
    return json.loads((DEMO_DATA / "cities.json").read_text())


def default_city() -> str:
    return registry()["default"]


def city_ids() -> list[str]:
    return [c["id"] for c in registry()["cities"]]


def city_dir(city: str) -> Path:
    for c in registry()["cities"]:
        if c["id"] == city:
            return (DEMO_DATA / c["data_dir"]).resolve()
    raise KeyError(city)


def centre_label(city: str) -> str:
    for c in registry()["cities"]:
        if c["id"] == city:
            return c.get("centre_label") or c["name"]
    raise KeyError(city)


def resolve(city: str | None) -> str:
    """The requested city, or the default. Unknown ids are a clear 404 (never silently another city's data)."""
    city = city or default_city()
    if city not in city_ids():
        raise HTTPException(404, {"code": "unknown_city", "message": f"Unknown city '{city}'."})
    return city


@lru_cache
def map_source(city: str) -> dict:
    """Area and download details of the saved OpenStreetMap file a city's map was built from."""
    files = sorted(city_dir(city).glob("osm_*.json"))
    if not files:
        area_file = city_dir(city) / "area.json"
        area = json.loads(area_file.read_text()) if area_file.exists() else None
        return {"file": None, "area": area}
    meta = json.loads(files[-1].read_text()).get("shadowmap", {})
    return {
        "file": files[-1].name,
        "downloaded_at_utc": meta.get("downloaded_at_utc"),
        "osm_data_timestamp": meta.get("osm_data_timestamp"),
        "licence": meta.get("licence"),
        "area": meta.get("area"),
    }
