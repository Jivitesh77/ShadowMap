"""Street safety score, exactly as BLUEPRINT.md §7 and §10 describe. All point values live here.

S = w * S_photo + (1 - w) * S_map + R, with w = 0.5 ** (age_minutes / 60), clamped to 0..100.
Pure functions only (no database), so every rule is unit-tested.
"""

from dataclasses import dataclass

from app import config

# --- Map score (blueprint §7 "Map score") ---
ROAD_CLASS_POINTS = {"main": 60, "residential": 45, "lane": 35, "underpass": 25}
OPEN_PLACE_RADIUS_M = 50
OPEN_PLACE_POINTS = 5
OPEN_PLACE_MAX = 15
# Blueprint §4: places with unknown hours "count for less in the safety score than places confirmed open".
# The blueprint gives no number; 2 points is our starting value (see docs/KNOWN_ISSUES.md).
UNKNOWN_HOURS_PLACE_POINTS = 2
HELP_RADIUS_M = 200
HELP_POINTS = 10  # police station or hospital within 200 m
HELP_CATEGORIES = {"police", "hospital"}

# --- Photo score (blueprint §7 "Photo score") ---
LIGHTING_POINTS = {"bright": 40, "dim": 15, "dark": 0}
PEOPLE_POINTS = {"many": 25, "few": 12, "none": 0}
VISIBLE_OPEN_PLACE_POINTS = 5
VISIBLE_OPEN_PLACE_MAX = 15
VEHICLES_POINTS = 5  # "some" or "busy"
# Blueprint: "Lane, underpass or empty plot: -5 to -10". Lane is the milder case.
ISOLATION_POINTS = {"lane": -5, "underpass": -10, "empty plot": -10}
HAZARD_POINTS = -5
MAX_PHOTOS_AVERAGED = 5  # "the newest ones are averaged"

# --- Community reports (blueprint §10): effect and how long it lasts ---
REPORT_EFFECTS = {
    "broken_light": (-15, 7 * 24 * 60),
    "dark": (-15, 3 * 60),
    "deserted": (-10, 2 * 60),
    "felt_unsafe": (-10, 2 * 60),
    "well_lit": (10, 2 * 60),
}
# Blueprint §10: "two or more matching reports on the same stretch within an hour count more than one".
# The blueprint gives no number; 1.5x is our starting value (see docs/KNOWN_ISSUES.md).
AGREEMENT_WINDOW_MIN = 60
AGREEMENT_MULTIPLIER = 1.5


def clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


def colour(score: float) -> str:
    if score >= config.SCORE_GREEN_MIN:
        return "green"
    if score >= config.SCORE_YELLOW_MIN:
        return "yellow"
    return "red"


@dataclass
class NearbyPlace:
    category: str
    status: str  # open / closed / unknown at the time of the walk
    distance_m: float


def map_score(road_class: str, nearby: list[NearbyPlace]) -> float:
    score = ROAD_CLASS_POINTS.get(road_class, ROAD_CLASS_POINTS["lane"])
    place_points = 0
    for p in nearby:
        if p.distance_m <= OPEN_PLACE_RADIUS_M:
            if p.status == "open":
                place_points += OPEN_PLACE_POINTS
            elif p.status == "unknown":
                place_points += UNKNOWN_HOURS_PLACE_POINTS
    score += min(place_points, OPEN_PLACE_MAX)
    if any(p.category in HELP_CATEGORIES and p.distance_m <= HELP_RADIUS_M for p in nearby):
        score += HELP_POINTS
    return float(score)


@dataclass
class PhotoFields:
    lighting: str | None
    people: str | None
    open_places_count: int | None
    vehicles: str | None
    isolation: str | None
    hazards: list[str] | None


def photo_score(f: PhotoFields) -> float:
    score = LIGHTING_POINTS.get(f.lighting or "", 0) + PEOPLE_POINTS.get(f.people or "", 0)
    score += min((f.open_places_count or 0) * VISIBLE_OPEN_PLACE_POINTS, VISIBLE_OPEN_PLACE_MAX)
    if f.vehicles in ("some", "busy"):
        score += VEHICLES_POINTS
    score += ISOLATION_POINTS.get(f.isolation or "", 0)
    if any(h and h != "none" for h in (f.hazards or [])):
        score += HAZARD_POINTS
    return float(score)


def freshness_weight(age_minutes: float) -> float:
    """A photo's weight halves every 60 minutes (blueprint §7)."""
    return 0.5 ** (max(age_minutes, 0) / config.PHOTO_HALF_LIFE_MIN)


@dataclass
class Photo:
    score: float
    age_minutes: float
    lighting: str | None = None


@dataclass
class ReportIn:
    kind: str
    age_minutes: float


def report_adjustment(reports: list[ReportIn], newest_photo: Photo | None) -> float:
    """R in the formula. Faded reports are ignored, and a newer Sentinel photo outweighs a report:
    a broken-light report ends when a newer photo shows the street lit; other reports end at any newer photo."""
    by_kind: dict[str, list[float]] = {}
    for r in reports:
        if r.kind not in REPORT_EFFECTS:
            continue
        points, lasts = REPORT_EFFECTS[r.kind]
        if r.age_minutes > lasts:
            continue
        if newest_photo and newest_photo.age_minutes < r.age_minutes:
            if r.kind != "broken_light" or newest_photo.lighting in ("bright", "dim"):
                continue
        by_kind.setdefault(r.kind, []).append(r.age_minutes)
    total = 0.0
    for kind, ages in by_kind.items():
        points = REPORT_EFFECTS[kind][0]
        ages.sort()
        agree = any(ages[i + 1] - ages[i] <= AGREEMENT_WINDOW_MIN for i in range(len(ages) - 1))
        total += points * (AGREEMENT_MULTIPLIER if agree else 1)
    return total


@dataclass
class StreetScore:
    score: float
    colour: str
    map_score: float
    photo_score: float | None  # weighted average of recent photos, None if no photos
    weight: float  # w of the freshest photo, 0 if none
    report_adjustment: float
    freshest_photo_age_min: float | None


def street_score(m_score: float, photos: list[Photo], reports: list[ReportIn]) -> StreetScore:
    """Blueprint §7: S = w * S_photo + (1 - w) * S_map + R.
    With several photos, the newest ones are averaged, each weighted by its own freshness;
    w is the freshness of the newest photo, so the score slides back to the map score as photos age."""
    recent = sorted(photos, key=lambda p: p.age_minutes)[:MAX_PHOTOS_AVERAGED]
    if recent:
        weights = [freshness_weight(p.age_minutes) for p in recent]
        s_photo = sum(w * p.score for w, p in zip(weights, recent)) / sum(weights)
        w = weights[0]
    else:
        s_photo, w = None, 0.0
    r = report_adjustment(reports, recent[0] if recent else None)
    raw = (w * s_photo if s_photo is not None else 0.0) + (1 - w) * m_score + r
    s = clamp(raw)
    return StreetScore(
        score=round(s, 1),
        colour=colour(s),
        map_score=m_score,
        photo_score=round(s_photo, 1) if s_photo is not None else None,
        weight=round(w, 3),
        report_adjustment=r,
        freshest_photo_age_min=round(recent[0].age_minutes, 1) if recent else None,
    )


def safest_cost(length_m: float, score: float) -> float:
    """Blueprint §8: cost = length * (1 + 3 * (100 - S) / 100). Never below the length itself."""
    return length_m * (1 + config.SAFETY_COST_FACTOR * (100 - clamp(score)) / 100)
