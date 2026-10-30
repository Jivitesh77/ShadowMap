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


def cumulative_m(points: list[list[float]]) -> list[float]:
    out = [0.0]
    for i in range(len(points) - 1):
        out.append(out[-1] + haversine_m(*points[i], *points[i + 1]))
    return out


def locate_on_line(lat: float, lon: float, points: list[list[float]]) -> tuple[float, float, list[float]]:
    """Closest point on a polyline. Returns (distance_m, metres_along_line, [lat, lon] of that point)."""
    kx = math.cos(math.radians(lat)) * 111_320
    ky = 110_540
    cum = cumulative_m(points)
    best = (float("inf"), 0.0, points[0])
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        ax, ay = (a[1] - lon) * kx, (a[0] - lat) * ky
        dx, dy = (b[1] - a[1]) * kx, (b[0] - a[0]) * ky
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        d = math.hypot(ax + t * dx, ay + t * dy)
        if d < best[0]:
            point = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
            best = (d, cum[i] + t * (cum[i + 1] - cum[i]), point)
    return best


def cut_line(points: list[list[float]], start_m: float, end_m: float) -> list[list[float]]:
    """The part of a polyline between two distances along it (start_m <= end_m)."""
    cum = cumulative_m(points)

    def at(m: float) -> list[float]:
        for i in range(len(points) - 1):
            if cum[i + 1] >= m:
                seg = cum[i + 1] - cum[i]
                t = 0.0 if seg == 0 else (m - cum[i]) / seg
                a, b = points[i], points[i + 1]
                return [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]
        return list(points[-1])

    inner = [list(p) for p, c in zip(points, cum) if start_m < c < end_m]
    return [at(start_m), *inner, at(end_m)]
