"""Small distance helpers. Accurate enough for a few kilometres around the campus."""

import math

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def line_length_m(points: list[list[float]]) -> float:
    return sum(haversine_m(*points[i], *points[i + 1]) for i in range(len(points) - 1))


def point_to_line_m(lat: float, lon: float, points: list[list[float]]) -> float:
    """Shortest distance from a point to a polyline, using a flat projection around the point."""
    kx = math.cos(math.radians(lat)) * 111_320
    ky = 110_540

    def xy(p):
        return ((p[1] - lon) * kx, (p[0] - lat) * ky)

    best = float("inf")
    for a, b in zip(points, points[1:]):
        (ax, ay), (bx, by) = xy(a), xy(b)
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    if len(points) == 1:
        x, y = xy(points[0])
        best = math.hypot(x, y)
    return best
