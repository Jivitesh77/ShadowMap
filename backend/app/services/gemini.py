"""Minimal Gemini client (REST generateContent). The key stays on the server and is sent only in a header."""

import json
import urllib.error
import urllib.request

from app import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    pass


def configured() -> bool:
    return bool(config.GEMINI_API_KEY)


def generate_json(system: str, prompt: str, temperature: float = 0.2) -> dict:
    """Ask Gemini for a JSON answer. Raises GeminiError (never includes the key in messages)."""
    if not configured():
        raise GeminiError("Gemini key not set")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        URL.format(model=config.GEMINI_MODEL),
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": config.GEMINI_API_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=config.GEMINI_TIMEOUT_S) as res:
            data = json.load(res)
    except urllib.error.HTTPError as err:
        raise GeminiError(f"Gemini returned HTTP {err.code}")
    except (urllib.error.URLError, TimeoutError):
        raise GeminiError("Gemini could not be reached")
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        return json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError):
        raise GeminiError("Gemini gave an answer in the wrong format")
