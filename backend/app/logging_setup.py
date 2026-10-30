"""Backend logging: one format, warnings and errors always visible, and no trip-link secrets in any log line.

A walk's id is the secret part of the trusted contact's link (/trip/<id>, /api/walks/<id>/...), so it is never logged:
- our own messages use walk_ref(id), a short one-way fingerprint that still lets you follow one walk through the log;
- the web server's request log (one line per request) gets walk ids in paths replaced by the same fingerprint.
Names, phone numbers, positions, PINs, tokens and access codes are never logged, and database errors hide their SQL
values (db.py, hide_parameters). LOG_LEVEL (default INFO) sets how much ShadowMap's own loggers print.
"""

import hashlib
import logging
import os
import re
import sys

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# Walk ids are 16 random URL-safe characters; fixed routes such as /api/walks/config are shorter and stay readable.
_WALK_IN_PATH = re.compile(r"(/api/walks/|/trip/)([A-Za-z0-9_-]{12,})")


def walk_ref(walk_id: str | None) -> str:
    """Short one-way fingerprint of a walk id for logs: the same walk always gets the same reference,
    but the trip link cannot be rebuilt from it."""
    if not walk_id:
        return "walk-unknown"
    return "walk-" + hashlib.sha256(walk_id.encode()).hexdigest()[:10]


def redact_walk_paths(text: str) -> str:
    return _WALK_IN_PATH.sub(lambda m: m.group(1) + walk_ref(m.group(2)), text)


class RedactWalkIds(logging.Filter):
    """Replaces walk ids in request paths (uvicorn's access log passes the path as an argument) and in messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_walk_paths(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_walk_paths(a) if isinstance(a, str) else a for a in record.args)
        return True


def _level() -> int:
    name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = logging.getLevelNamesMapping().get(name)
    return level if isinstance(level, int) else logging.INFO  # an unknown value never silences warnings


def setup_logging() -> None:
    """Safe to call more than once (tests, --reload): handlers and filters are added only once."""
    ours = logging.getLogger("shadowmap")
    ours.setLevel(min(_level(), logging.WARNING))  # warnings and errors stay visible whatever LOG_LEVEL says
    if not any(getattr(h, "shadowmap_handler", False) for h in ours.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler.addFilter(RedactWalkIds())
        handler.shadowmap_handler = True
        ours.addHandler(handler)
    for name in ("uvicorn.access", "uvicorn.error"):
        server_log = logging.getLogger(name)
        if not any(isinstance(f, RedactWalkIds) for f in server_log.filters):
            server_log.addFilter(RedactWalkIds())
