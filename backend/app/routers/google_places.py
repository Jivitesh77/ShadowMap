"""Optional, supplementary place search with Google Places API (New) — Nearby Search.

Rules (Google Maps Platform terms, checked 2026-10-30, and owner instructions):
- Results are NEVER drawn on the Leaflet/OpenStreetMap map and never merged with OSM or ShadowMap places.
  They are returned for a separate list with "Google Maps" attribution and a link to open each place in Google Maps.
- Nothing from Google is stored: no database, no cache, no log of results. Coordinates are used only to
  compute a distance for this one response and are not sent to the screen.
- The API key lives only in backend/.env and is sent to Google in a header, never in a URL or to the browser.
- Without a key the feature reports "not configured" and the rest of ShadowMap is unaffected.
- Only basic ("Pro") fields are requested; opening hours are a more expensive field and are left out.
"""

import json
import time
import urllib.error
import urllib.request
from collections import deque

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.services.geo import haversine_m

router = APIRouter(prefix="/api/google-places")

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.googleMapsUri", "places.primaryType", "places.businessStatus",
])
# Google "Table A" place types -> ShadowMap categories (for labels in the list only).
TYPES = {
    "police": "police",
    "hospital": "hospital",
    "doctor": "clinic",
    "pharmacy": "pharmacy",
    "gas_station": "fuel",
    "atm": "atm",
    "bus_station": "transit",
    "convenience_store": "food_shop",
    "lodging": "hotel",
}
ATTRIBUTION = "Google Maps"

_recent_calls: deque[float] = deque()  # timestamps only, for the hourly limit; no Google content


class NearbyRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: int = Field(default=2000, ge=100, le=10000)
    categories: list[str] | None = None  # ShadowMap categories; default: all in TYPES


@router.get("/status")
def status():
    return {"configured": bool(config.GOOGLE_PLACES_API_KEY), "attribution": ATTRIBUTION}


def _check_limit() -> None:
    now = time.time()
    while _recent_calls and now - _recent_calls[0] > 3600:
        _recent_calls.popleft()
    if len(_recent_calls) >= config.GOOGLE_PLACES_MAX_PER_HOUR:
        raise HTTPException(429, {"code": "limit", "message": "Google search limit for this hour reached. Try again later."})
    _recent_calls.append(now)


@router.post("/nearby")
def nearby(req: NearbyRequest):
    if not config.GOOGLE_PLACES_API_KEY:
        raise HTTPException(503, {"code": "not_configured",
                                  "message": "Google Places search is not set up. ShadowMap is using OpenStreetMap and team-verified places."})
    wanted = req.categories or list(set(TYPES.values()))
    types = [t for t, cat in TYPES.items() if cat in wanted]
    if not types:
        raise HTTPException(400, {"code": "bad_categories", "message": "None of those categories can be searched on Google."})
    _check_limit()

    body = {
        "includedTypes": types,
        "maxResultCount": 20,
        "rankPreference": "DISTANCE",
        "locationRestriction": {"circle": {"center": {"latitude": req.lat, "longitude": req.lon}, "radius": float(req.radius_m)}},
    }
    request = urllib.request.Request(
        NEARBY_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": config.GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as res:
            data = json.load(res)
    except urllib.error.HTTPError as err:
        raise HTTPException(502, {"code": "google_error", "message": f"Google Places returned an error (HTTP {err.code})."})
    except (urllib.error.URLError, TimeoutError):
        raise HTTPException(502, {"code": "google_unreachable", "message": "Could not reach Google Places."})

    results = []
    for p in data.get("places", []):
        loc = p.get("location") or {}
        distance = None
        if "latitude" in loc and "longitude" in loc:
            distance = round(haversine_m(req.lat, req.lon, loc["latitude"], loc["longitude"]))
        results.append({
            "place_id": p.get("id"),
            "name": (p.get("displayName") or {}).get("text"),
            "address": p.get("formattedAddress"),
            "google_type": p.get("primaryType"),
            "category": TYPES.get(p.get("primaryType") or ""),
            "business_status": p.get("businessStatus"),
            "google_maps_uri": p.get("googleMapsUri"),
            "distance_m": distance,
        })
    results.sort(key=lambda r: (r["distance_m"] is None, r["distance_m"] or 0))
    return {
        "source": "google",
        "attribution": ATTRIBUTION,
        "radius_m": req.radius_m,
        "results": results,
        "notes": [
            "From Google Maps. Not checked by ShadowMap, not shown on the ShadowMap map, and not saved.",
            "Opening hours are not fetched; open the place in Google Maps to check them.",
        ],
    }
