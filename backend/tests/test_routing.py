"""Dijkstra shortest vs safest on small hand-made street networks near (26.0, 91.0)."""

import pytest

from app.services.geo import haversine_m, line_length_m
from app.services.routing import RouteError, StreetEdge, build_graph, dijkstra, path_length, plan, same_path

LAT, LON = 26.0, 91.0


def edge(sid, a, b, pa, pb):
    geom = [[LAT + pa[0], LON + pa[1]], [LAT + pb[0], LON + pb[1]]]
    return StreetEdge(sid, a, b, line_length_m(geom), geom)


def network(detour_offset):
    """Top: A-B-C straight (red). Bottom: A-D-E-F-C detour (green), `detour_offset` degrees south."""
    o = detour_offset
    return [
        edge(1, 1, 2, (0, 0), (0, 0.001)),  # A-B
        edge(2, 2, 3, (0, 0.001), (0, 0.002)),  # B-C
        edge(3, 1, 4, (0, 0), (-o, 0)),  # A-D
        edge(4, 4, 5, (-o, 0), (-o, 0.001)),  # D-E
        edge(5, 5, 6, (-o, 0.001), (-o, 0.002)),  # E-F
        edge(6, 6, 3, (-o, 0.002), (0, 0.002)),  # F-C
    ]


SCORES = {1: 10, 2: 10, 3: 90, 4: 90, 5: 90, 6: 90}
START, END = (LAT, LON + 0.0001), (LAT, LON + 0.0019)


def streets_of(steps):
    return [s.edge.street_id for s in steps]


def test_safest_avoids_red_street_within_detour_limit():
    # shortest = 180 m along the red top road; detour = 10 + 22 + 200 + 22 + 10 = ~265 m (< 1.5 x 180)
    pair = plan(network(0.0002), SCORES, START, END)
    assert set(streets_of(pair.shortest)) == {1, 2}
    # start and end points sit on the red streets 1 and 2, so only those first/last ~10 m are red
    assert set(streets_of(pair.safest)) == {1, 2, 3, 4, 5, 6}
    red_m = sum(st.edge.length_m for st in pair.safest if st.edge.street_id in (1, 2))
    assert red_m == pytest.approx(20, abs=1)
    assert pair.safest_within_limit
    assert path_length(pair.safest) <= 1.5 * path_length(pair.shortest)
    # real distances: shortest is the straight 180 m between the two points
    assert path_length(pair.shortest) == pytest.approx(haversine_m(*START, *END), rel=0.01)


def test_detour_limit_falls_back_when_safe_way_is_too_long():
    pair = plan(network(0.0004), SCORES, START, END)  # detour ~309 m > 1.5 x 180 m
    assert not pair.safest_within_limit
    assert path_length(pair.safest) <= 1.5 * path_length(pair.shortest) + 1e-6
    assert same_path(pair.safest, pair.shortest)  # no alternative inside the limit: no invented route


def test_single_road_has_no_alternative():
    road = [edge(1, 1, 2, (0, 0), (0, 0.001)), edge(2, 2, 3, (0, 0.001), (0, 0.002))]
    pair = plan(road, {1: 10, 2: 10}, START, END)
    assert same_path(pair.shortest, pair.safest)


def test_disconnected_roads():
    roads = [edge(1, 1, 2, (0, 0), (0, 0.0008)), edge(2, 3, 4, (0, 0.0012), (0, 0.002))]
    with pytest.raises(RouteError) as err:
        plan(roads, {1: 50, 2: 50}, START, END)
    assert err.value.code == "not_connected"


def test_point_far_from_any_street():
    with pytest.raises(RouteError) as err:
        plan(network(0.0004), SCORES, START, (LAT + 0.01, LON))  # ~1.1 km away
    assert err.value.code == "too_far"


def test_same_place():
    with pytest.raises(RouteError) as err:
        plan(network(0.0004), SCORES, START, START)
    assert err.value.code == "same_place"


def test_both_points_on_one_street_walk_straight_along_it():
    road = [edge(1, 1, 2, (0, 0), (0, 0.002))]
    pair = plan(road, {1: 50}, (LAT, LON + 0.0005), (LAT, LON + 0.0015))
    assert path_length(pair.shortest) == pytest.approx(100, rel=0.02)
    assert streets_of(pair.shortest) == [1]


def test_route_geometry_is_continuous():
    pair = plan(network(0.0004), SCORES, START, END)
    prev_end = None
    for step in pair.safest:
        g = step.geometry
        if prev_end is not None:
            assert haversine_m(*prev_end, *g[0]) < 0.5
        prev_end = g[-1]


def test_dijkstra_rejects_negative_costs():
    g = build_graph(network(0.0004))
    with pytest.raises(ValueError):
        dijkstra(g, 1, 3, lambda e: -1)
