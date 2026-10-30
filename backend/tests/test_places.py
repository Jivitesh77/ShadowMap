"""Careful matching between OpenStreetMap entries and ShadowMap's own checks, and confidence levels."""

from datetime import date

from app import models
from app.services.places import Candidate, best_match, confidence, match_reason, name_similarity, normalise_name
from scripts.build_map import build_osm_places, merge_verified

BOX = {"south": 26.07, "west": 91.55, "north": 26.09, "east": 91.57}
M = 1 / 111_200  # one metre of latitude in degrees


def c(key, name, cat, dlat_m=0.0):
    return Candidate(key, name, cat, 26.08 + dlat_m * M, 91.56)


def test_names_are_normalised():
    assert normalise_name("Baba Ganesh  Medicos!") == "baba ganesh medicos"
    assert normalise_name("The Canteen") == "canteen"
    assert name_similarity("Guwahati Netralaya Eye Hospital", "Guwahati Netralaya eye hospital") == 1.0
    assert name_similarity(None, "x") == 0.0


def test_match_rules():
    assert match_reason(c("a", "Baba Ganesh Medicos", "pharmacy"), c("b", "Baba Ganesh Medicos", "pharmacy", 50))
    assert match_reason(c("a", "Baba Ganesh Medicos", "pharmacy"), c("b", "Baba Ganesh Medicos", "pharmacy", 80)) is None  # too far
    assert match_reason(c("a", "Ganesh Medicos", "pharmacy"), c("b", "Baba Ganesh Medicos", "pharmacy", 20))  # similar + near
    assert match_reason(c("a", "Ganesh Medicos", "pharmacy"), c("b", "Baba Ganesh Medicos", "pharmacy", 40))  # one name inside the other
    assert match_reason(c("a", "Sharma Medicos", "pharmacy"), c("b", "Verma Medicos", "pharmacy", 10)) is None  # different shops
    assert match_reason(c("a", "Ranjita", "food_shop"), c("b", "Ranjeeta Restaurant", "food_shop", 30))  # spelling variant
    assert match_reason(c("a", "Medical Store", "pharmacy"), c("b", "Medical Store", "pharmacy", 30))  # identical generic names
    assert match_reason(c("a", "Medical Store", "pharmacy"), c("b", "Medicos", "pharmacy", 10)) is None
    assert match_reason(c("a", "Sharma Tea Stall", "food_shop"), c("b", "Sharma General Store", "food_shop", 5)) is None  # kinds conflict
    assert match_reason(c("a", "Sharma Tea Stall", "food_shop"), c("b", "Gupta Tea Stall", "food_shop", 10)) is None  # neighbours
    assert match_reason(c("a", "Hari Om Sharma Tea", "food_shop"), c("b", "Sharma Bros Tea", "food_shop", 20))  # shared word, near
    assert match_reason(c("a", "Hari Om Sharma Tea", "food_shop"), c("b", "Sharma Bros Tea", "food_shop", 40)) is None  # not near enough
    assert match_reason(c("a", "Apollo Pharmacy", "pharmacy"), c("b", "City Medicos", "pharmacy", 5)) is None  # different names, same spot
    assert match_reason(c("a", "Azara Hospital", "pharmacy"), c("b", "Azara Hospital", "police", 5)) is None  # different kind of place
    assert match_reason(c("a", "Azara Rural Hospital", "clinic"), c("b", "Azara Rural Hospital", "hospital", 10))  # clinic ~ hospital
    assert match_reason(c("a", None, "atm"), c("b", "SBI", "atm", 10))  # unnamed: same category within 15 m
    assert match_reason(c("a", None, "atm"), c("b", "SBI", "atm", 20)) is None


def test_best_match_prefers_most_similar_and_respects_taken():
    pool = [c("x", "Ranjeeta Hotel", "food_shop", 10), c("y", "Ranjeeta", "food_shop", 30)]
    m = best_match(c("v", "Ranjeeta", "food_shop"), pool, set())
    assert m[0].key == "y"
    assert best_match(c("v", "Ranjeeta", "food_shop"), pool, {"y"}) is None or best_match(c("v", "Ranjeeta", "food_shop"), pool, {"y"})[0].key == "x"


def test_confidence_levels():
    today = date(2026, 10, 30)
    assert confidence(["shadowmap"], "X", "2026-10-25", None, today)[0] == "high"
    assert confidence(["shadowmap"], "X", "2026-06-01", None, today)[0] == "medium"
    assert confidence(["shadowmap"], "X", "2025-01-01", None, today)[0] == "low"
    assert confidence(["osm"], "Ranjeeta", None, "2021-05-02T10:00:00Z", today) == (
        "medium", "Listed on OpenStreetMap, last edited 2021; not checked by the ShadowMap team")
    assert confidence(["osm"], None, None, None, today)[0] == "low"
    assert confidence(["osm"], "X", None, None, today)[0] != "high"  # OSM alone is never high
    assert confidence(["osm", "shadowmap"], "X", "2025-01-01", None, today)[0] == "medium"  # better of the two


def _osm(eid, name, amenity, dlat_m, extra=None):
    return {"type": "node", "id": eid, "lat": 26.08 + dlat_m * M, "lon": 91.56, "timestamp": "2024-01-02T00:00:00Z",
            "tags": {"amenity": amenity, **({"name": name} if name else {}), **(extra or {})}}


def test_osm_duplicates_merged_but_unnamed_neighbours_kept():
    els = [
        _osm(1, "Guwahati Netralaya Eye Hospital", "hospital", 0, {"phone": "1"}),
        _osm(2, "Guwahati Netralaya eye hospital", "hospital", 30),
        _osm(3, None, "atm", 0),
        _osm(4, None, "atm", 5),
    ]
    places = build_osm_places(els, BOX)
    hospitals = [p for p in places if p.category == "hospital"]
    assert len(hospitals) == 1 and hospitals[0].osm_id == "node/1" and hospitals[0].duplicate_osm_ids == ["node/2"]
    assert len([p for p in places if p.category == "atm"]) == 2  # cannot be sure two unnamed ATMs are one
    assert hospitals[0].sources == ["osm"] and hospitals[0].osm_last_edited == "2024-01-02T00:00:00Z"


def test_verified_places_merge_or_add():
    osm = build_osm_places([_osm(10, "Baba Ganesh Medicos", "pharmacy", 0), _osm(11, "Ranjeeta", "restaurant", 500)], BOX)
    verified = [
        {"name": "Baba Ganesh Medicos", "category": "pharmacy", "lat": 26.08 + 20 * M, "lon": 91.56, "opening_hours": "Mo-Su 08:00-22:00",
         "verified_by": "Field lead", "verified_on": "2026-10-29", "in_demo_area": True},
        {"name": "New Tea Stall", "category": "food_shop", "lat": 26.081, "lon": 91.561,
         "verified_by": "Field lead", "verified_on": "2026-10-29", "in_demo_area": True},
        {"name": "Ranjeeta Restaurant", "category": "food_shop", "lat": 26.0, "lon": 91.0, "osm_id": "node/11",
         "verified_by": "Field lead", "verified_on": "2026-10-29", "in_demo_area": False},
    ]
    places, log = merge_verified(osm, verified)
    by_name = {p.name: p for p in places}
    merged = by_name["Baba Ganesh Medicos"]
    assert merged.sources == ["osm", "shadowmap"] and merged.osm_id == "node/10" and merged.hours_source == "shadowmap"
    assert merged.match_note == "same name, 20 m apart"
    assert by_name["New Tea Stall"].sources == ["shadowmap"] and by_name["New Tea Stall"].osm_id is None
    assert by_name["Ranjeeta Restaurant"].osm_id == "node/11" and "linked by the team" in by_name["Ranjeeta Restaurant"].match_note
    assert len(places) == 3 and len(log) == 3
