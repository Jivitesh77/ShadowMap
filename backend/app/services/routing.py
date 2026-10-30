"""Street graph + Dijkstra (blueprint §8). No database here, so it can be tested on hand-made graphs.

Every street segment is an edge between two junction nodes. Walking ignores one-way rules.
Start and end points are placed on the nearest street and joined to the graph as temporary nodes.
"""

import heapq
from dataclasses import dataclass, field
from typing import Callable

from app import config
from app.services.geo import cut_line, haversine_m, locate_on_line
from app.services.scoring import safest_cost

START, END = -1, -2  # ids of the temporary nodes for the chosen points
MAX_SNAP_M = 250  # a point further than this from every mapped street cannot be routed
# If the blueprint's safest route is more than 50% longer, try gentler safety weightings (still >= length).
FALLBACK_FACTORS = [2, 1.5, 1, 0.5, 0.25]


class RouteError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class StreetEdge:
    street_id: int
    start_node: int
    end_node: int
    length_m: float
    geometry: list[list[float]]


@dataclass
class Edge:
    a: int
    b: int
    street_id: int
    length_m: float
    geometry: list[list[float]]  # from a to b


@dataclass
class Graph:
    edges: list[Edge] = field(default_factory=list)
    adj: dict[int, list[int]] = field(default_factory=dict)  # node -> edge indexes

    def add(self, e: Edge) -> None:
        self.edges.append(e)
        i = len(self.edges) - 1
        self.adj.setdefault(e.a, []).append(i)
        self.adj.setdefault(e.b, []).append(i)

    def copy(self) -> "Graph":
        return Graph(list(self.edges), {k: list(v) for k, v in self.adj.items()})


def build_graph(streets: list[StreetEdge]) -> Graph:
    g = Graph()
    for s in streets:
        if s.length_m > 0 and len(s.geometry) >= 2:
            g.add(Edge(s.start_node, s.end_node, s.street_id, s.length_m, s.geometry))
    return g


@dataclass
class Snap:
    street: StreetEdge
    along_m: float
    distance_m: float
    point: list[float]


def snap(streets: list[StreetEdge], lat: float, lon: float) -> Snap:
    best: Snap | None = None
    for s in streets:
        d, along, point = locate_on_line(lat, lon, s.geometry)
        if best is None or d < best.distance_m:
            best = Snap(s, along, d, point)
    if best is None or best.distance_m > MAX_SNAP_M:
        raise RouteError("too_far", f"That point is more than {MAX_SNAP_M} m from any mapped street.")
    return best


def _attach(g: Graph, node: int, sn: Snap) -> None:
    s, total = sn.street, sn.street.length_m
    along = min(max(sn.along_m, 0.0), total)
    g.add(Edge(s.start_node, node, s.street_id, along, cut_line(s.geometry, 0, along)))
    g.add(Edge(node, s.end_node, s.street_id, total - along, cut_line(s.geometry, along, total)))


def with_endpoints(g: Graph, start: Snap, end: Snap) -> Graph:
    h = g.copy()
    _attach(h, START, start)
    _attach(h, END, end)
    if start.street.street_id == end.street.street_id:  # both on one street: walk straight along it
        a, b = sorted([start.along_m, end.along_m])
        geom = cut_line(start.street.geometry, a, b)
        if start.along_m > end.along_m:
            geom = geom[::-1]
        h.add(Edge(START, END, start.street.street_id, b - a, geom))
    return h


@dataclass
class Step:
    edge: Edge
    forward: bool  # walked from a to b

    @property
    def geometry(self) -> list[list[float]]:
        return self.edge.geometry if self.forward else self.edge.geometry[::-1]


def dijkstra(g: Graph, src: int, dst: int, cost: Callable[[Edge], float]) -> list[Step] | None:
    """Lowest total cost path from src to dst. Costs must be >= 0 (ours are always >= the length)."""
    best = {src: 0.0}
    prev: dict[int, tuple[int, int]] = {}  # node -> (edge index, previous node)
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            break
        if d > best.get(u, float("inf")):
            continue
        for i in g.adj.get(u, []):
            e = g.edges[i]
            v = e.b if e.a == u else e.a
            c = cost(e)
            if c < 0:
                raise ValueError("negative edge cost")
            nd = d + c
            if nd < best.get(v, float("inf")):
                best[v] = nd
                prev[v] = (i, u)
                heapq.heappush(heap, (nd, v))
    if dst not in best:
        return None
    steps, node = [], dst
    while node != src:
        i, p = prev[node]
        e = g.edges[i]
        steps.append(Step(e, forward=(e.a == p)))
        node = p
    return steps[::-1]


def path_length(steps: list[Step]) -> float:
    return sum(s.edge.length_m for s in steps)


@dataclass
class RoutePair:
    shortest: list[Step]
    safest: list[Step]
    safest_within_limit: bool  # False = the blueprint's safest route was too long; a gentler one was used
    start: Snap
    end: Snap


def plan(streets: list[StreetEdge], scores: dict[int, float], start: tuple[float, float], end: tuple[float, float]) -> RoutePair:
    g = build_graph(streets)
    s_snap, e_snap = snap(streets, *start), snap(streets, *end)
    if haversine_m(*s_snap.point, *e_snap.point) < 5:
        raise RouteError("same_place", "Start and destination are the same place.")
    h = with_endpoints(g, s_snap, e_snap)

    shortest = dijkstra(h, START, END, lambda e: e.length_m)
    if shortest is None:
        raise RouteError("not_connected", "No mapped streets connect these two points.")

    def weighted(factor: float):
        return lambda e: e.length_m * (1 + factor * (100 - scores.get(e.street_id, 0)) / 100)

    safest = dijkstra(h, START, END, lambda e: safest_cost(e.length_m, scores.get(e.street_id, 0)))
    limit = config.MAX_DETOUR_RATIO * path_length(shortest)
    within = path_length(safest) <= limit + 1e-6
    if not within:
        for f in FALLBACK_FACTORS:
            candidate = dijkstra(h, START, END, weighted(f))
            if candidate and path_length(candidate) <= limit + 1e-6:
                safest = candidate
                break
        else:
            safest = shortest
    return RoutePair(shortest, safest, within, s_snap, e_snap)


def same_path(a: list[Step], b: list[Step]) -> bool:
    return [(s.edge.street_id, s.forward, round(s.edge.length_m, 1)) for s in a] == [
        (s.edge.street_id, s.forward, round(s.edge.length_m, 1)) for s in b
    ]
