"""Combining place sources carefully: OpenStreetMap entries and ShadowMap's own in-person checks.

Two entries are only treated as the same place when the evidence is strong (see `match_reason`).
Google Places content never comes through here: it is not stored and never merged (Google terms).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from app.services.geo import haversine_m

# Categories that can describe the same real place (e.g. a team member says "clinic", OSM says "hospital").
_GROUPS = [{"hospital", "clinic"}]
_STOPWORDS = {"the", "and", "of"}
# Words that say what kind of place it is, not which one. "Sharma Medicos" and "Verma Medicos" must not match.
_GENERIC = {
    "medicos", "medical", "medicals", "medicine", "pharmacy", "chemist", "chemists", "drug", "drugs", "store", "stores",
    "shop", "hospital", "clinic", "nursing", "home", "centre", "center", "diagnostic", "diagnostics", "police", "station",
    "outpost", "post", "thana", "petrol", "pump", "fuel", "filling", "atm", "bank", "restaurant", "hotel", "dhaba",
    "tea", "stall", "canteen", "bus", "stop", "general", "and", "co", "pvt", "ltd",
}

# Matching distances. Conservative on purpose: a wrong merge would hide a real place.
SAME_NAME_M = 60  # distinctive words agree: up to 60 m apart
SHARED_WORD_M = 25  # at least one distinctive word in common: up to 25 m apart
UNNAMED_M = 15  # one side has no name: same category and within 15 m
NAMED_FAR_SIM = 0.8  # spelling-variant threshold for distinctive words (e.g. "Ranjeeta" / "Ranjita")


def normalise_name(name: str | None) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(w for w in text.split() if w not in _STOPWORDS)


def name_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    jaccard = len(ta & tb) / len(ta | tb)
    return max(SequenceMatcher(None, na, nb).ratio(), jaccard)


def distinctive(name: str | None) -> set[str]:
    return {w for w in normalise_name(name).split() if w not in _GENERIC}


def same_name(a: str | None, b: str | None) -> bool:
    """Distinctive words agree: equal, one set inside the other, or a near-identical spelling."""
    da, db = distinctive(a), distinctive(b)
    if not da or not db:  # only generic words, e.g. "Medical Store": compare the whole name exactly
        return bool(normalise_name(a)) and normalise_name(a) == normalise_name(b)
    if da <= db or db <= da:
        return True
    return SequenceMatcher(None, " ".join(sorted(da)), " ".join(sorted(db))).ratio() >= NAMED_FAR_SIM


def shares_word(a: str | None, b: str | None) -> bool:
    return bool(distinctive(a) & distinctive(b))


def kinds_conflict(a: str | None, b: str | None) -> bool:
    """Both names say what kind of place they are, with no word in common ("Tea Stall" vs "General Store")."""
    ga = {w for w in normalise_name(a).split() if w in _GENERIC}
    gb = {w for w in normalise_name(b).split() if w in _GENERIC}
    return bool(ga) and bool(gb) and not (ga & gb)


def compatible(cat_a: str, cat_b: str) -> bool:
    return cat_a == cat_b or any(cat_a in g and cat_b in g for g in _GROUPS)


@dataclass
class Candidate:
    key: str  # e.g. "node/123"
    name: str | None
    category: str
    lat: float
    lon: float


def match_reason(a: Candidate, b: Candidate) -> str | None:
    """Why a and b are the same place, or None if the evidence is not strong enough."""
    if not compatible(a.category, b.category):
        return None
    d = haversine_m(a.lat, a.lon, b.lat, b.lon)
    if a.name and b.name:
        if kinds_conflict(a.name, b.name):
            return None
        if d <= SAME_NAME_M and same_name(a.name, b.name):
            return f"same name, {d:.0f} m apart"
        if d <= SHARED_WORD_M and shares_word(a.name, b.name):
            return f"similar name, {d:.0f} m apart"
        return None
    if a.category == b.category and d <= UNNAMED_M:
        return f"same category, {d:.0f} m apart (one has no name)"
    return None


def best_match(item: Candidate, pool: list[Candidate], taken: set[str]) -> tuple[Candidate, str] | None:
    """The closest strong match in `pool` that has not been matched yet."""
    found = []
    for c in pool:
        if c.key in taken:
            continue
        reason = match_reason(item, c)
        if reason:
            found.append((-name_similarity(item.name, c.name), haversine_m(item.lat, item.lon, c.lat, c.lon), c, reason))
    if not found:
        return None
    found.sort(key=lambda x: (x[0], x[1]))
    return found[0][2], found[0][3]


# --- Confidence that the place exists as described (not a safety rating) ---
RECENT_DAYS = 30
OLDER_DAYS = 180


def confidence(sources: list[str], name: str | None, verified_on: str | None, osm_last_edited: str | None,
               today: date) -> tuple[str, str]:
    """(level, reason). Levels: high / medium / low. Rules:
    - Checked in person by the team within 30 days: high; within 180 days: medium; older: low.
    - OpenStreetMap only: medium if it has a name, low if it has no name. Never high: nobody from ShadowMap checked it.
    - Both: the better of the two."""
    levels = {"low": 0, "medium": 1, "high": 2}
    options: list[tuple[str, str]] = []
    if "shadowmap" in sources and verified_on:
        try:
            age = (today - date.fromisoformat(verified_on)).days
        except ValueError:
            age = None
        if age is not None and age <= RECENT_DAYS:
            options.append(("high", f"Checked in person by the ShadowMap team {age} days ago"))
        elif age is not None and age <= OLDER_DAYS:
            options.append(("medium", f"Checked in person by the ShadowMap team {age} days ago"))
        else:
            options.append(("low", "Team check is more than 6 months old or has no valid date"))
    if "osm" in sources:
        year = (osm_last_edited or "")[:4]
        edited = f", last edited {year}" if year else ""
        if name:
            options.append(("medium", f"Listed on OpenStreetMap{edited}; not checked by the ShadowMap team"))
        else:
            options.append(("low", f"Unnamed OpenStreetMap entry{edited}; not checked by the ShadowMap team"))
    if not options:
        return "low", "No source information"
    level, reason = max(options, key=lambda o: levels[o[0]])
    if len(sources) > 1:
        reason += "; also listed on OpenStreetMap" if "osm" in sources and "Checked" in reason else ""
    return level, reason
