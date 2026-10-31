"""Per-client request limits for the expensive public endpoints (agreed 2026-10-31).

Route planning 30 / min, help-point search 30 / min, walk start 5 / min, AI route briefing 10 / min per client
(agreed 2026-10-31); reports 120 / hour, map 240 / min and where-am-I 120 / min per client (finalization; sized so a
class sharing one hotspot is not blocked). Configurable
with RATE_LIMIT_* (0 = off). Above a limit the answer is HTTP 429 with a Retry-After header.
Reports also keep their own 5 per hour per device; the per-connection limit stops a client that invents device ids.

How a "client" is recognised (client_ip): the direct connection address, or, behind a trusted proxy (TRUSTED_PROXY_HOPS,
Render = 1), the X-Forwarded-For entry that proxy appended. Entries further left are written by the client itself and
are never used, so a faked header cannot dodge a limit. The city is not part of the key: switching cities does not
give a fresh allowance. Safety actions during a walk (position, PIN answer, SOS, end) are never limited.

Counts are kept in memory (a sliding one-minute window per client and endpoint). That fits the single-process design
(render.yaml: 1 instance): they reset when the server restarts, and two server processes would each count separately.
"""

import math
import threading
import time
from collections import deque
from typing import Callable

from fastapi import HTTPException, Request

from app import config

WINDOW_S = 60.0  # default window
MAX_KEYS = 50_000  # memory bound: idle clients are dropped when this many are tracked
LABELS = {"route": "route requests", "help_point": "help-point searches", "walk_start": "walk starts",
          "briefing": "route briefings", "report": "reports", "map": "map loads", "where_am_i": "location look-ups"}
# Window per category. Reports use an hour: a per-minute window would still allow hundreds of reports an hour.
WINDOWS_S = {"report": 3600.0}


class SlidingWindowLimiter:
    """At most `limit` accepted requests per key in any WINDOW_S seconds. Refused requests are not counted, so a client
    that keeps retrying is let in again as soon as its oldest accepted request is a minute old."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._hits: dict[tuple, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: tuple, limit: int, window_s: float = WINDOW_S) -> float | None:
        """Record a request. Returns None if allowed, otherwise the seconds until the next request is allowed."""
        now = self.clock()
        with self._lock:
            times = self._hits.setdefault(key, deque())
            while times and now - times[0] >= window_s:
                times.popleft()
            if len(times) >= limit:
                return window_s - (now - times[0])
            times.append(now)
            if len(self._hits) > MAX_KEYS:
                self._drop_idle(now)
            return None

    def _drop_idle(self, now: float) -> None:
        longest = max([WINDOW_S, *WINDOWS_S.values()])
        for key in [k for k, t in self._hits.items() if not t or now - t[-1] >= longest]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """The client address used for limits. Only the proxy-appended part of X-Forwarded-For is trusted."""
    direct = request.client.host if request.client else "unknown"
    hops = config.TRUSTED_PROXY_HOPS
    if hops <= 0:
        return direct
    hosts = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if len(hosts) < hops:
        return direct  # did not come through the expected proxies: never trust the header
    return hosts[-hops]


def rate_limit(category: str):
    """FastAPI dependency: `dependencies=[Depends(rate_limit("route"))]`. Every accepted request counts, including ones
    that then fail validation or planning, so invalid requests cannot be used to hammer the server either."""
    if category not in LABELS:
        raise ValueError(f"unknown rate-limit category {category!r}")

    def check(request: Request) -> None:
        limit = config.RATE_LIMITS.get(category, 0)
        if limit <= 0:
            return
        window = WINDOWS_S.get(category, WINDOW_S)
        wait = limiter.hit((category, client_ip(request)), limit, window)
        if wait is not None:
            seconds = max(1, math.ceil(wait))
            period = "hour" if window >= 3600 else "minute"
            wait_text = f"{math.ceil(seconds / 60)} minutes" if seconds >= 120 else f"{seconds} seconds"
            raise HTTPException(
                429,
                {"code": "rate_limited", "retry_after_s": seconds,
                 "message": f"Too many {LABELS[category]} from this network in the last {period} (limit {limit}). "
                            f"Please wait {wait_text} and try again."},
                headers={"Retry-After": str(seconds)},
            )

    check.__name__ = f"rate_limit_{category}"
    return check
