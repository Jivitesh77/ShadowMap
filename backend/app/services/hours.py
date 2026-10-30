"""Is a place open at a given time? Reads the common OpenStreetMap `opening_hours` formats.

Supported: "24/7", "08:00-22:00", "Mo-Su 08:00-23:00", "Mo-Fr 09:00-17:00; Sa 10:00-14:00",
"Mo,We,Fr 09:00-13:00,14:00-18:00", "Su off", ranges past midnight ("18:00-02:00").
Anything else returns "unknown" — we never guess.
"""

import re
from datetime import datetime

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

# Blueprint §4 suggested treating these as open 24 h when no hours are listed. Owner decision (2026-10-30):
# never assume a place is open because hours are missing. They stay "unknown"; the screen may only add a hint.
USUALLY_24H = {"police", "hospital", "hotel"}

_TIME = r"(\d{1,2}):(\d{2})"
_RANGE = re.compile(rf"^{_TIME}\s*-\s*{_TIME}\+?$")
_DAYSPEC = re.compile(r"^(Mo|Tu|We|Th|Fr|Sa|Su)(-(Mo|Tu|We|Th|Fr|Sa|Su))?$")


class Unparseable(Exception):
    pass


def _days(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        m = _DAYSPEC.match(part.strip())
        if not m:
            raise Unparseable(part)
        a = DAYS.index(m.group(1))
        b = DAYS.index(m.group(3)) if m.group(3) else a
        i = a
        while True:  # handles wrap-around like Sa-Mo
            out.add(i)
            if i == b:
                break
            i = (i + 1) % 7
    return out


def _ranges(spec: str) -> list[tuple[int, int]]:
    out = []
    for part in spec.split(","):
        m = _RANGE.match(part.strip())
        if not m:
            raise Unparseable(part)
        h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 24 or h2 > 48 or m1 > 59 or m2 > 59:
            raise Unparseable(part)
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:
            end += 24 * 60  # closes after midnight
        out.append((start, end))
    return out


def parse(text: str) -> dict[int, list[tuple[int, int]]]:
    """Weekday (0=Mo) -> list of (start_minute, end_minute). Later rules override earlier ones, as in OSM."""
    text = text.strip()
    if text == "24/7":
        return {d: [(0, 24 * 60)] for d in range(7)}
    week: dict[int, list[tuple[int, int]]] = {d: [] for d in range(7)}
    rules = [r.strip() for r in text.split(";") if r.strip()]
    if not rules:
        raise Unparseable(text)
    for rule in rules:
        if rule.startswith("PH"):
            continue  # public holidays: ignored in the prototype
        parts = rule.split(None, 1)
        if _DAYSPEC.match(parts[0].split(",")[0]):
            days = _days(parts[0])
            rest = parts[1].strip() if len(parts) > 1 else ""
        else:
            days, rest = set(range(7)), rule
        if rest in ("off", "closed"):
            ranges = []
        elif rest in ("24/7", "00:00-24:00"):
            ranges = [(0, 24 * 60)]
        else:
            ranges = _ranges(rest)
        for d in days:
            week[d] = ranges
    return week


def status_at(opening_hours: str | None, category: str, at: datetime) -> tuple[str, str]:
    """Returns (status, basis).

    status: "open" / "closed" / "unknown"
    basis:  "listed"   — from the place's own hours
            "missing"  — no hours listed (never assumed open, whatever the category)
            "unreadable" — hours listed in a format we cannot read
    """
    if not opening_hours:
        return "unknown", "missing"
    try:
        week = parse(opening_hours)
    except Unparseable:
        return "unknown", "unreadable"

    minute = at.hour * 60 + at.minute
    today = at.weekday()
    yesterday = (today - 1) % 7
    if any(s <= minute < e for s, e in week[today]):
        return "open", "listed"
    if any(e > 24 * 60 and minute < e - 24 * 60 for _, e in week[yesterday]):
        return "open", "listed"  # still open from last night
    return "closed", "listed"
