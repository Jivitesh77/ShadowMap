"""Route briefing (blueprint §8): 4-6 plain sentences about a route, in English or Hindi.

Only facts from ShadowMap's own data are used. With a Gemini key, Gemini writes the text and every sentence must
cite fact ids; the text is then checked (no names, numbers or "safe" claims that are not in the facts). Without a
key, or if the check fails, a summary is built directly from the facts and labelled as such — never as AI.
"""

import json
import re

from app.services import gemini

CATEGORY_EN = {"police": "police station", "hospital": "hospital", "clinic": "clinic", "pharmacy": "pharmacy",
               "fuel": "petrol pump", "atm": "ATM", "transit": "bus/train stop", "food_shop": "shop or eatery", "hotel": "hotel"}
CATEGORY_HI = {"police": "पुलिस स्टेशन", "hospital": "अस्पताल", "clinic": "क्लिनिक", "pharmacy": "दवा की दुकान",
               "fuel": "पेट्रोल पंप", "atm": "एटीएम", "transit": "बस/ट्रेन स्टॉप", "food_shop": "दुकान या भोजनालय", "hotel": "होटल"}
CLASS_EN = {"main": "main road", "residential": "residential street", "lane": "lane", "underpass": "underpass"}
CLASS_HI = {"main": "मुख्य सड़क", "residential": "रिहायशी गली", "lane": "गली", "underpass": "अंडरपास"}
REPORT_EN = {"broken_light": "broken streetlight", "dark": "dark here", "deserted": "deserted", "felt_unsafe": "felt unsafe",
             "well_lit": "well lit and busy"}
REPORT_HI = {"broken_light": "स्ट्रीटलाइट खराब", "dark": "यहाँ अंधेरा", "deserted": "सुनसान", "felt_unsafe": "असुरक्षित महसूस हुआ",
             "well_lit": "रोशनी और लोग"}


def build_facts(route: dict, other: dict, same_route: bool, at: str, observations: dict[int, dict],
                reports: dict[int, list[dict]], names: dict[int, str | None]) -> dict:
    """Facts for the safest route. `route` and `other` are route summaries from /api/route (safest, shortest).
    observations: street_id -> latest analysed observation {age_min, lighting, people, open_places, description, sentinel}
    reports: street_id -> active reports [{kind, age_min}]"""
    segments = []
    for seg in route["segments"]:
        name = names.get(seg["street_id"])
        key = name or f"unnamed {seg['road_class']}"
        if segments and segments[-1]["_key"] == key:  # merge consecutive pieces of the same road
            last = segments[-1]
            last["length_m"] += seg["length_m"]
            last["street_ids"].append(seg["street_id"])
            last["score"] = min(last["score"], seg["score"])
            continue
        segments.append({"_key": key, "name": name, "road_class": seg["road_class"], "length_m": seg["length_m"],
                         "score": seg["score"], "colour": seg["colour"], "street_ids": [seg["street_id"]]})
    out_segments = []
    for i, s in enumerate(segments, start=1):
        obs = [observations[sid] for sid in s["street_ids"] if sid in observations]
        newest = min(obs, key=lambda o: o["age_min"]) if obs else None
        reps = [r for sid in s["street_ids"] for r in reports.get(sid, [])]
        out_segments.append({
            "id": f"S{i}", "name": s["name"], "road_class": s["road_class"], "length_m": round(s["length_m"]),
            "colour": s["colour"], "score": round(s["score"]),
            "latest_photo": newest and {k: newest[k] for k in ("age_min", "lighting", "people", "open_places", "description", "sentinel")},
            "community_reports": [{"kind": r["kind"], "age_min": r["age_min"]} for r in reps],
        })
    places = [{"id": f"P{i}", "name": p["name"], "category": p["category"], "status": p["status"],
               "hours_known": p["status_basis"] in ("listed", "community"), "distance_from_route_m": p["distance_m"]}
              for i, p in enumerate(route["places_passed"], start=1)]
    return {
        "walk": {"id": "W", "walk_time": at, "distance_m": route["distance_m"], "duration_min": route["duration_min"],
                 "red_m": route["red_m"], "same_as_shortest": same_route,
                 "shortest_distance_m": other["distance_m"], "shortest_red_m": other["red_m"]},
        "segments": out_segments,
        "places": places,
        "has_photos": any(s["latest_photo"] for s in out_segments),
    }


# ---------------- summary built directly from the facts (no AI) ----------------

def _age_en(m: float) -> str:
    m = round(m)
    return f"{m} minutes ago" if m < 60 else f"{m // 60} h {m % 60} min ago"


def _age_hi(m: float) -> str:
    m = round(m)
    return f"{m} मिनट पहले" if m < 60 else f"{m // 60} घंटे {m % 60} मिनट पहले"


def _seg_name(s: dict, lang: str) -> str:
    if s["name"]:
        return s["name"]
    return ("an unnamed " + CLASS_EN[s["road_class"]]) if lang == "en" else ("एक बिना नाम की " + CLASS_HI[s["road_class"]])


def template_briefing(f: dict, lang: str) -> list[str]:
    w = f["walk"]
    km = w["distance_m"] / 1000
    photo_segs = sorted([s for s in f["segments"] if s["latest_photo"]], key=lambda s: s["latest_photo"]["age_min"])
    reported = [(s, r) for s in f["segments"] for r in s["community_reports"]]
    out = []
    if lang == "hi":
        out.append(f"आपका रास्ता {km:.1f} किलोमीटर का है, लगभग {w['duration_min']} मिनट पैदल।")
        if photo_segs:
            s = photo_segs[0]
            p = s["latest_photo"]
            out.append(f"{_seg_name(s, 'hi')} की तस्वीर {_age_hi(p['age_min'])} ली गई थी: {p['description'] or ''}".strip())
        else:
            out.append("इस रास्ते की कोई ताज़ा तस्वीर नहीं है; जानकारी सिर्फ़ नक्शे से है।")
        out.append(f"रास्ते का {w['red_m']} मीटर लाल (जोखिम वाली) सड़कों पर है।" if w["red_m"] else "रास्ते का कोई भी हिस्सा लाल सड़कों पर नहीं है।")
        if f["places"]:
            parts = [f"{p['name'] or CATEGORY_HI[p['category']]} ({'समय अज्ञात' if not p['hours_known'] else ('खुला' if p['status'] == 'open' else 'बंद')})" for p in f["places"][:4]]
            out.append("रास्ते में ये जगहें हैं: " + ", ".join(parts) + "।")
        else:
            out.append("इस रास्ते पर कोई दर्ज जगह नहीं है।")
        if reported:
            s, r = reported[0]
            out.append(f"{_seg_name(s, 'hi')} पर {_age_hi(r['age_min'])} एक रिपोर्ट आई: \"{REPORT_HI.get(r['kind'], r['kind'])}\"।")
        out.append("यह सबसे छोटा रास्ता भी है।" if w["same_as_shortest"] else f"सबसे छोटा रास्ता {w['shortest_distance_m']} मीटर का है और उसमें {w['shortest_red_m']} मीटर लाल सड़कें हैं।")
        return out[:6]
    out.append(f"Your route is {km:.1f} km, about {w['duration_min']} minutes on foot.")
    if photo_segs:
        s = photo_segs[0]
        p = s["latest_photo"]
        out.append(f"{_seg_name(s, 'en')} was photographed by {p['sentinel']} {_age_en(p['age_min'])}: {p['description'] or 'no description'}.")
    else:
        out.append("I don't have fresh street photos of this route; the scores come from map data only.")
    out.append(f"{w['red_m']} m of the route is on streets marked red." if w["red_m"] else "None of the route is on streets marked red.")
    if f["places"]:
        parts = [f"{p['name'] or 'a ' + CATEGORY_EN[p['category']]} ({'hours unknown' if not p['hours_known'] else p['status']})" for p in f["places"][:4]]
        out.append("You pass " + ", ".join(parts) + ".")
    else:
        out.append("No places are recorded along this route.")
    if reported:
        s, r = reported[0]
        out.append(f"Someone reported \"{REPORT_EN.get(r['kind'], r['kind'])}\" on {_seg_name(s, 'en')} {_age_en(r['age_min'])}.")
    out.append("This is also the shortest route." if w["same_as_shortest"]
               else f"The shortest route is {w['shortest_distance_m']} m with {w['shortest_red_m']} m on red streets.")
    return out[:6]


# ---------------- AI briefing with checks ----------------

SYSTEM = """You write a short walking-route briefing for ShadowMap, a night-safety map.
Rules (all mandatory):
- Use ONLY the facts given. Never mention a street, shop, police station, light, person or observation that is not in the facts.
- Every observation you mention must say how old it is (e.g. "6 minutes ago"), using age_min from the facts.
- If there are no photos (latest_photo is null everywhere), say the information comes from map data only.
- Never say the route or any place is "safe". You may say "safer" and describe conditions and choices.
- Unnamed roads: call them "an unnamed road" (or the Hindi equivalent). Do not invent names.
- Only use numbers that appear in the facts (you may round metres to km with one decimal).
- Write 4 to 6 short sentences. Language: {lang}. In Hindi, keep street and place names exactly as given, in English letters, and use digits 0-9.
Answer as JSON: {"sentences": [{"text": "...", "fact_ids": ["W", "S1", "P2"]}]}. Every sentence cites at least one fact id."""


def _numbers_in(obj) -> set[str]:
    found = set()
    for n in re.findall(r"\d+(?:\.\d+)?", json.dumps(obj, ensure_ascii=False)):
        found.add(n)
        try:
            v = float(n)
            found.update({str(round(v)), f"{v / 1000:.1f}", f"{v / 60:.0f}", str(int(v // 60)), str(int(v % 60))})
        except ValueError:
            pass
    return found


def check_ai_text(sentences: list[dict], facts: dict, gazetteer: set[str], lang: str) -> list[str]:
    """Problems with an AI answer; empty list = acceptable."""
    problems = []
    if not 3 <= len(sentences) <= 7:
        problems.append(f"{len(sentences)} sentences")
    ids = {"W"} | {s["id"] for s in facts["segments"]} | {p["id"] for p in facts["places"]}
    fact_names = {s["name"].lower() for s in facts["segments"] if s["name"]} | {p["name"].lower() for p in facts["places"] if p["name"]}
    allowed_numbers = _numbers_in(facts) | {str(i) for i in range(0, 7)}
    for s in sentences:
        text = s.get("text", "")
        cited = s.get("fact_ids") or []
        if not cited or any(c not in ids for c in cited):
            problems.append(f"bad citation in: {text[:60]}")
        low = text.lower()
        for name in gazetteer:
            if len(name) >= 3 and name not in fact_names and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", low):
                problems.append(f"mentions '{name}', which is not on this route")
        for n in re.findall(r"\d+(?:\.\d+)?", text):
            if n not in allowed_numbers:
                problems.append(f"number {n} is not in the facts")
        if lang == "en" and re.search(r"\bsafe\b", low):
            problems.append("calls something 'safe'")
        if lang == "hi" and re.search(r"(?<!अधिक )सुरक्षित (है|हैं)", text):
            problems.append("calls something 'safe' (Hindi)")
    return problems


def make_briefing(facts: dict, lang: str, gazetteer: set[str]) -> dict:
    """Returns {text, sentences, source: 'ai' | 'data', note}."""
    if gemini.configured():
        prompt = "Facts (JSON):\n" + json.dumps(facts, ensure_ascii=False)
        system = SYSTEM.replace("{lang}", "Hindi" if lang == "hi" else "English")
        last_problems: list[str] = []
        for attempt in range(2):
            try:
                answer = gemini.generate_json(system, prompt if attempt == 0 else prompt + "\nYour previous answer broke these rules: " + "; ".join(last_problems[:5]))
                sentences = answer.get("sentences") or []
                last_problems = check_ai_text(sentences, facts, gazetteer, lang)
                if not last_problems:
                    texts = [s["text"].strip() for s in sentences]
                    return {"text": " ".join(texts), "sentences": texts, "source": "ai", "note": None}
            except gemini.GeminiError as err:
                last_problems = [str(err)]
                break
        texts = template_briefing(facts, lang)
        return {"text": " ".join(texts), "sentences": texts, "source": "data",
                "note": "The AI briefing did not pass ShadowMap's fact check, so this summary is built directly from the data."
                        if last_problems and "Gemini" not in last_problems[0] else f"AI unavailable ({last_problems[0] if last_problems else 'unknown'}); summary built from the data."}
    texts = template_briefing(facts, lang)
    return {"text": " ".join(texts), "sentences": texts, "source": "data",
            "note": "AI briefing is not set up (no Gemini key); this summary is built directly from ShadowMap's data."}
