"""Guards the Sentinel video upload while it arrives (KNOWN_ISSUES #100).

FastAPI reads the whole upload form into a temporary buffer before the endpoint (and its access-code check) runs, so a
size check inside the endpoint comes too late. This guard runs first, for POST /api/sentinel/videos/uploads only:
1. no or wrong Sentinel access code -> 401 / 403 before a single byte of the video is read;
2. announced size (Content-Length) above the limit -> 413 at once;
3. not enough room on the data disk (DISK_RESERVE_MB must stay free) -> 507 at once;
4. while the bytes arrive they are counted; past the limit reading stops -> 413. The web server's buffer is closed and
   freed (Starlette closes it on MultiPartException), and the endpoint never runs, so no file is written.
The endpoint itself still checks the exact file size (the limit includes the file only, not the form around it).
"""

import json

from fastapi import HTTPException
from starlette.formparsers import MultiPartException

from app import config
from app.services import storage

UPLOAD_PATH = "/api/sentinel/videos/uploads"


class UploadTooLarge(MultiPartException):
    """A MultiPartException, so Starlette's form reader closes (and frees) its temporary files when it is raised."""


def too_large_detail() -> dict:
    return {"code": "too_large",
            "message": f"Videos larger than {config.MAX_VIDEO_UPLOAD_MB} MB are not supported. Trim the video to the ride "
                       "(or a shorter part of it) and upload that."}


def disk_full_detail() -> dict:
    return {"code": "disk_full",
            "message": "There is not enough storage space for this video right now. Older photos and videos are removed "
                       "automatically after 6 hours; try a shorter video or try again later."}


async def send_json(send, status: int, detail) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class UploadGuard:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path") != UPLOAD_PATH:
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

        from app.routers.sentinel import require_access  # same rule and messages as every other Sentinel endpoint
        try:
            require_access(headers.get("x-sentinel-token"))
        except HTTPException as e:
            return await send_json(send, e.status_code, e.detail)

        body_limit = config.MAX_VIDEO_UPLOAD_BYTES + config.UPLOAD_FORM_OVERHEAD_BYTES
        try:
            declared = int(headers["content-length"])
        except (KeyError, ValueError):
            declared = None
        if declared is not None and declared > body_limit:
            return await send_json(send, 413, too_large_detail())
        if not storage.has_room(declared if declared is not None else config.MAX_VIDEO_UPLOAD_BYTES):
            return await send_json(send, 507, disk_full_detail())

        received, over, started = 0, False, False

        async def counted_receive():
            nonlocal received, over
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit:
                    over = True
                    raise UploadTooLarge(too_large_detail()["message"])
            return message

        async def guarded_send(message):
            nonlocal started
            if over:  # whatever the app answers to the stopped upload, the client gets the clear 413
                if message["type"] == "http.response.start" and not started:
                    started = True
                    await send_json(send, 413, too_large_detail())
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, guarded_send)
        except UploadTooLarge:
            if not started:
                await send_json(send, 413, too_large_detail())
