"""Blueprint §7 and §10 rules, checked number by number."""

import pytest

from app.services.scoring import (
    NearbyPlace, Photo, PhotoFields, ReportIn, clamp, colour, freshness_weight, map_score,
    photo_score, report_adjustment, safest_cost, street_score,
)


def test_map_score_road_classes():
    assert [map_score(c, []) for c in ("main", "residential", "lane", "underpass")] == [60, 45, 35, 25]


def test_map_score_open_places_capped_and_unknown_counts_less():
    four_open = [NearbyPlace("pharmacy", "open", 20)] * 4
    assert map_score("residential", four_open) == 45 + 15  # +5 each, max +15
    assert map_score("residential", [NearbyPlace("food_shop", "unknown", 30)]) == 47
    assert map_score("residential", [NearbyPlace("food_shop", "closed", 30)]) == 45
    assert map_score("residential", [NearbyPlace("pharmacy", "open", 60)]) == 45  # beyond 50 m


def test_map_score_police_or_hospital_within_200m():
    assert map_score("lane", [NearbyPlace("police", "open", 150)]) == 45  # police beyond 50 m: only the +10
    assert map_score("lane", [NearbyPlace("hospital", "open", 199)]) == 45
    assert map_score("lane", [NearbyPlace("police", "open", 201)]) == 35


def test_photo_score_fields():
    best = PhotoFields("bright", "many", 4, "busy", "market", ["none"])
    assert photo_score(best) == 40 + 25 + 15 + 5
    worst = PhotoFields("dark", "none", 0, "none", "underpass", ["broken road"])
    assert photo_score(worst) == 0 + 0 - 10 - 5
    assert photo_score(PhotoFields("dim", "few", 1, "some", "lane", [])) == 15 + 12 + 5 + 5 - 5


def test_freshness_halves_every_hour():
    assert freshness_weight(0) == 1
    assert freshness_weight(60) == pytest.approx(0.5)
    assert freshness_weight(120) == pytest.approx(0.25)


def test_score_formula_and_decay_back_to_map():
    assert street_score(60, [], []).score == 60  # map data only
    fresh = street_score(60, [Photo(0, 10)], [])  # dark empty street seen 10 min ago
    w = 0.5 ** (10 / 60)
    assert fresh.score == pytest.approx(round(w * 0 + (1 - w) * 60, 1))
    assert fresh.colour == "red"
    old = street_score(60, [Photo(0, 600)], [])  # 10 hours later: nearly back to the map score
    assert old.score >= 59.9


def test_several_photos_averaged_by_freshness():
    sc = street_score(50, [Photo(80, 0), Photo(20, 60)], [])
    s_photo = (1 * 80 + 0.5 * 20) / 1.5
    assert sc.photo_score == pytest.approx(round(s_photo, 1))
    assert sc.score == pytest.approx(round(1 * s_photo + 0 * 50, 1))


def test_reports_effects_fading_and_agreement():
    assert report_adjustment([ReportIn("broken_light", 30)], None) == -15
    assert report_adjustment([ReportIn("dark", 200)], None) == 0  # dark fades after 3 h
    assert report_adjustment([ReportIn("well_lit", 10)], None) == 10
    assert report_adjustment([ReportIn("dark", 10), ReportIn("dark", 40)], None) == -22.5  # agreement
    assert report_adjustment([ReportIn("dark", 10), ReportIn("dark", 100)], None) == -15  # 90 min apart
    assert report_adjustment([ReportIn("broken_light", 8 * 24 * 60)], None) == 0  # 7 days


def test_newer_photo_outweighs_reports():
    assert report_adjustment([ReportIn("deserted", 30)], Photo(50, 5, "dim")) == 0
    assert report_adjustment([ReportIn("broken_light", 30)], Photo(10, 5, "dark")) == -15  # still dark
    assert report_adjustment([ReportIn("broken_light", 30)], Photo(60, 5, "bright")) == 0  # now lit
    assert report_adjustment([ReportIn("dark", 3)], Photo(50, 30, "dim")) == -15  # report is newer


def test_clamp_and_colours():
    assert clamp(-12) == 0 and clamp(140) == 100
    # 10 - 22.5 (two agreeing "dark" reports) - 10 ("deserted") = -22.5 -> clamped to 0
    assert street_score(10, [], [ReportIn("dark", 1), ReportIn("dark", 2), ReportIn("deserted", 5)]).score == 0
    assert [colour(x) for x in (100, 70, 69.9, 40, 39.9, 0)] == ["green", "green", "yellow", "yellow", "red", "red"]


def test_safest_cost_never_below_length():
    assert safest_cost(100, 100) == 100
    assert safest_cost(100, 0) == 400
    assert safest_cost(100, 50) == 250
    assert safest_cost(100, -20) == 400  # scores are clamped first
