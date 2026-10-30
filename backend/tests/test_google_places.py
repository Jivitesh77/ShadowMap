"""Google Places stays optional, server-side, uncached and separate from our data."""

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, models
from app.db import engine
from app.main import app
from app.routers import google_places

FAKE_KEY = "test-key-not-real"
GOOGLE_REPLY = {"places": [
    {"id": "ChIJfar", "displayName": {"text": "Far Hospital"}, "formattedAddress": "Azara, Assam",
     "location": {"latitude": 26.11, "longitude": 91.56}, "googleMapsUri": "https://maps.google.com/?cid=1",
     "primaryType": "hospital", "businessStatus": "OPERATIONAL"},
    {"id": "ChIJnear", "displayName": {"text": "Near Pharmacy"}, "formattedAddress": "NH17",
     "location": {"latitude": 26.081, "longitude": 91.56}, "googleMapsUri": "https://maps.google.com/?cid=2",
     "primaryType": "pharmacy", "businessStatus": "OPERATIONAL"},
]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def client():
    google_places._recent_calls.clear()
    with TestClient(app) as c:
        yield c


def row_counts():
    with Session(engine) as db:
        return [db.scalar(select(func.count()).select_from(m)) for m in (models.Place, models.Street, models.Observation)]


def test_without_key_feature_is_off_and_app_unaffected(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", "")
    assert client.get("/api/google-places/status").json()["configured"] is False
    res = client.post("/api/google-places/nearby", json={"lat": 26.08, "lon": 91.56})
    assert res.status_code == 503 and res.json()["detail"]["code"] == "not_configured"
    assert client.get("/api/map").status_code == 200  # rest of the app works


def test_request_keeps_key_in_header_and_results_are_not_stored(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", FAKE_KEY)
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["headers"], seen["body"] = req.full_url, dict(req.header_items()), json.loads(req.data)
        return FakeResponse(json.dumps(GOOGLE_REPLY).encode())

    monkeypatch.setattr(google_places.urllib.request, "urlopen", fake_urlopen)
    before = row_counts()
    res = client.post("/api/google-places/nearby", json={"lat": 26.08, "lon": 91.56, "radius_m": 5000})
    assert res.status_code == 200
    body = res.json()

    assert FAKE_KEY not in seen["url"] and seen["headers"]["X-goog-api-key"] == FAKE_KEY
    mask = seen["headers"]["X-goog-fieldmask"]
    assert "currentOpeningHours" not in mask and "reviews" not in mask and "places.googleMapsUri" in mask
    assert seen["body"]["locationRestriction"]["circle"]["radius"] == 5000.0

    assert body["attribution"] == "Google Maps" and body["source"] == "google"
    assert [r["name"] for r in body["results"]] == ["Near Pharmacy", "Far Hospital"]  # sorted by distance
    assert body["results"][0]["distance_m"] == 111
    assert all("lat" not in r and "location" not in r for r in body["results"])  # no coordinates to the screen
    assert FAKE_KEY not in res.text
    assert row_counts() == before  # nothing written to our database


def test_google_errors_are_reported_without_leaking_the_key(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", FAKE_KEY)

    def failing(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"API key not valid"))

    monkeypatch.setattr(google_places.urllib.request, "urlopen", failing)
    res = client.post("/api/google-places/nearby", json={"lat": 26.08, "lon": 91.56})
    assert res.status_code == 502 and FAKE_KEY not in res.text and "403" in res.json()["detail"]["message"]


def test_hourly_limit(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", FAKE_KEY)
    monkeypatch.setattr(config, "GOOGLE_PLACES_MAX_PER_HOUR", 2)
    monkeypatch.setattr(google_places.urllib.request, "urlopen", lambda req, timeout: FakeResponse(b'{"places": []}'))
    codes = [client.post("/api/google-places/nearby", json={"lat": 26.08, "lon": 91.56}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_bad_input(client, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_PLACES_API_KEY", FAKE_KEY)
    assert client.post("/api/google-places/nearby", json={"lat": 26.08, "lon": 91.56, "radius_m": 60000}).status_code == 422
    assert client.post("/api/google-places/nearby", json={"lat": 26.08, "lon": 91.56, "categories": ["temple"]}).status_code == 400
