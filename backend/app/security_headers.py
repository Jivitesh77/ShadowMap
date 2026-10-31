"""Security headers on every backend response (the API returns JSON and blurred photos; it never needs to be framed,
run scripts or use the camera / location itself — the frontend does that from its own origin).

- Referrer-Policy: no-referrer — a trip page's address is never passed on to another site.
- X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Permissions-Policy: nothing for the API itself.
- Content-Security-Policy: nothing may load from API responses; the automatic API pages (/docs, /redoc), which load
  their own scripts, are left out (they are switched off when hosted: API_DOCS=false).
- Strict-Transport-Security only when the request arrived over https (behind a proxy: X-Forwarded-Proto).
- App pages (one-container hosting: everything outside /api and /ws) get the frontend's headers instead: camera and
  location for this site only, and framing only by this site and the Hugging Face Space page that shows the app.
"""

DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
BASE = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]
CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
API_PATHS = ("/api", "/ws")
PAGE = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(self), geolocation=(self), microphone=(), payment=(), usb=()"),
    (b"content-security-policy", b"frame-ancestors 'self' https://huggingface.co"),
]
HSTS = (b"strict-transport-security", b"max-age=31536000")


class SecurityHeaders:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = dict(scope.get("headers", []))
        https = scope.get("scheme") == "https" or headers.get(b"x-forwarded-proto", b"").split(b",")[0].strip() == b"https"
        if path.startswith(API_PATHS) or path.startswith(DOCS_PATHS):
            extra = BASE + ([] if path.startswith(DOCS_PATHS) else [CSP])
        else:
            extra = PAGE
        extra = extra + ([HSTS] if https else [])

        async def with_headers(message):
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [h for h in extra if h[0] not in present]
            await send(message)

        await self.app(scope, receive, with_headers)
