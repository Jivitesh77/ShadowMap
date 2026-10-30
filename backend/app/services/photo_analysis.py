"""Gemini analysis of a Sentinel photo (blueprint §6). Backend only; the image sent is the REDACTED one.

The model describes the place, never the people: no age, gender, religion, clothing or intentions, only how many.
Its answer must match a fixed format; anything else is rejected (and retried by the worker).
It also reports any face or number plate it can still see after our blurring, so the photo is only shown
publicly when both our detector and the model agree nothing identifying remains (fail closed).
"""

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

LIGHTING = {"bright", "dim", "dark"}
PEOPLE = {"none", "few", "many"}
VEHICLES = {"none", "some", "busy"}
ISOLATION = {"open road", "lane", "underpass", "empty plot", "market"}
CONFIDENCE = {"low", "medium", "high"}
HAZARDS = {"broken road", "construction", "flooding", "stray dogs", "obstruction", "poor visibility", "none"}
PLACE_TYPES = {"shop", "eatery", "pharmacy", "fuel", "atm", "police", "hospital", "bus stop", "other"}
# Words that would describe people rather than the place. The description must not contain them.
PERSONAL_WORDS = re.compile(
    r"\b(man|men|woman|women|girl|girls|boy|boys|child|children|kid|kids|lady|ladies|gentleman|elderly|old|young|teen|teenager|"
    r"muslim|hindu|christian|sikh|religious|beggar|drunk|suspicious|criminal|thief|thieves|gang|couple|wearing|dressed)\b", re.I)

SYSTEM = """You analyse ONE street photo for a night-safety map. Describe the PLACE, never the people.
Never guess or mention anyone's age, gender, religion, ethnicity, clothing, appearance, identity or intentions. Only count people.
If the photo is too blurry, dark-noisy or blocked to judge, set "unclear": true.
Faces and number plates in the photo have been blurred on purpose. Report in "privacy" how many faces are still clearly
recognisable and how many number plates are still readable despite that blurring (0 if none).
Answer ONLY with this JSON:
{"unclear": bool,
 "lighting": "bright"|"dim"|"dark",
 "streetlights_visible": int, "streetlights_working": int,
 "people": "none"|"few"|"many",
 "open_places_count": int, "open_places_types": ["shop"|"eatery"|"pharmacy"|"fuel"|"atm"|"police"|"hospital"|"bus stop"|"other"],
 "vehicles": "none"|"some"|"busy",
 "isolation": "open road"|"lane"|"underpass"|"empty plot"|"market",
 "hazards": ["broken road"|"construction"|"flooding"|"stray dogs"|"obstruction"|"poor visibility"|"none"],
 "description": "one plain sentence about the street only",
 "confidence": "low"|"medium"|"high",
 "uncertainty": "what could not be judged, or empty",
 "privacy": {"unredacted_faces": int, "legible_number_plates": int}}"""


class AnalysisError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # no_key / rate_limited / timeout / http / invalid
        self.message = message


@dataclass
class Analysis:
    unclear: bool
    lighting: str | None = None
    streetlights_visible: int | None = None
    streetlights_working: int | None = None
    people: str | None = None
    open_places_count: int | None = None
    open_places_types: list[str] | None = None
    vehicles: str | None = None
    isolation: str | None = None
    hazards: list[str] | None = None
    description: str | None = None
    confidence: str | None = None
    uncertainty: str | None = None
    unredacted_faces: int = 0
    legible_plates: int = 0


def _int(v, lo=0, hi=50) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise AnalysisError("invalid", f"expected a whole number {lo}-{hi}, got {v!r}")
    return v


def _one(v, allowed: set[str]) -> str:
    if not isinstance(v, str) or v not in allowed:  # also rejects lists, dicts, numbers (no TypeError)
        raise AnalysisError("invalid", f"{v!r} is not one of {sorted(allowed)}")
    return v


def _text_list(v, allowed: set[str], limit: int) -> list[str]:
    if not isinstance(v, list) or len(v) > 20:
        raise AnalysisError("invalid", "expected a short list of words")
    return [_one(item, allowed) for item in v][:limit]


def validate(raw) -> Analysis:
    """Strictly check the model's JSON. Any unexpected shape becomes AnalysisError('invalid', ...), never another error."""
    try:
        return _validate(raw)
    except AnalysisError:
        raise
    except Exception as err:  # e.g. TypeError / AttributeError from a structure nobody expected
        raise AnalysisError("invalid", f"unexpected answer structure ({type(err).__name__})")


def _validate(raw) -> Analysis:
    if not isinstance(raw, dict) or not isinstance(raw.get("unclear"), bool):
        raise AnalysisError("invalid", "answer is not the expected JSON object")
    privacy = raw.get("privacy")
    if not isinstance(privacy, dict):
        raise AnalysisError("invalid", "privacy check missing")
    faces, plates = _int(privacy.get("unredacted_faces")), _int(privacy.get("legible_number_plates"))
    if raw["unclear"]:
        return Analysis(unclear=True, unredacted_faces=faces, legible_plates=plates)
    visible, working = _int(raw.get("streetlights_visible")), _int(raw.get("streetlights_working"))
    if working > visible:
        raise AnalysisError("invalid", "more working streetlights than visible ones")
    types = _text_list(raw.get("open_places_types", []), PLACE_TYPES, 10)
    hazards = _text_list(raw.get("hazards", ["none"]), HAZARDS, 6) or ["none"]
    description = raw.get("description")
    if not isinstance(description, str) or not 0 < len(description.strip()) <= 240:
        raise AnalysisError("invalid", "description missing or too long")
    if PERSONAL_WORDS.search(description):
        raise AnalysisError("invalid", "description talks about people, not the place")
    uncertainty = raw.get("uncertainty") or ""
    if not isinstance(uncertainty, str) or len(uncertainty) > 240 or PERSONAL_WORDS.search(uncertainty):
        raise AnalysisError("invalid", "uncertainty note invalid")
    return Analysis(
        unclear=False,
        lighting=_one(raw.get("lighting"), LIGHTING),
        streetlights_visible=visible,
        streetlights_working=working,
        people=_one(raw.get("people"), PEOPLE),
        open_places_count=_int(raw.get("open_places_count"), 0, 20),
        open_places_types=types,
        vehicles=_one(raw.get("vehicles"), VEHICLES),
        isolation=_one(raw.get("isolation"), ISOLATION),
        hazards=hazards,
        description=description.strip(),
        confidence=_one(raw.get("confidence"), CONFIDENCE),
        uncertainty=uncertainty.strip() or None,
        unredacted_faces=faces,
        legible_plates=plates,
    )


def analyse(jpeg_bytes: bytes) -> Analysis:
    """Send a redacted JPEG to Gemini and return the validated analysis. Raises AnalysisError."""
    if not config.GEMINI_API_KEY:
        raise AnalysisError("no_key", "Gemini key not set")
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(jpeg_bytes).decode()}},
            {"text": "Analyse this street photo."},
        ]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(URL.format(model=config.GEMINI_MODEL), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=config.GEMINI_TIMEOUT_S) as res:
            data = json.load(res)
    except urllib.error.HTTPError as err:
        if err.code == 429:
            raise AnalysisError("rate_limited", "Gemini rate limit reached")
        raise AnalysisError("http", f"Gemini returned HTTP {err.code}")
    except (urllib.error.URLError, TimeoutError):
        raise AnalysisError("timeout", "Gemini could not be reached in time")
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        raw = json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise AnalysisError("invalid", "Gemini's answer was not valid JSON")
    return validate(raw)
