"""Ring simplification and assembly of projected rings into Features."""

import numpy as np
import pytest

from packbuild.polygons import signed_area, simplify_ring, to_feature
from packbuild.projection import STATCAN_LAMBERT


def _square(x0, y0, size, per_edge=1, clockwise=True):
    corners = [(x0, y0), (x0, y0 + size), (x0 + size, y0 + size), (x0 + size, y0)]
    if not clockwise:
        corners = corners[::-1]
    pts = []
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1], strict=True):
        for k in range(per_edge):
            f = k / per_edge
            pts.append((ax + f * (bx - ax), ay + f * (by - ay)))
    pts.append(pts[0])
    return np.array(pts)


def test_signed_area_is_negative_for_clockwise_rings():
    assert signed_area(_square(0, 0, 10)) == pytest.approx(-100)
    assert signed_area(_square(0, 0, 10, clockwise=False)) == pytest.approx(100)


def test_simplify_drops_collinear_points_and_keeps_corners():
    ring = _square(7_000_000, 900_000, 1000, per_edge=25)
    assert len(ring) == 101
    out = simplify_ring(ring, 1.0)
    assert sorted(map(tuple, out.tolist())) == sorted(map(tuple, ring[[0, 25, 50, 75]].tolist()))
    assert signed_area(out) < 0  # orientation kept


def test_simplify_keeps_detail_larger_than_the_tolerance():
    ring = _square(0, 0, 1000, per_edge=4)
    ring[2] = (ring[2][0] + 30, ring[2][1])  # a 30 m bump on the west edge
    assert len(simplify_ring(ring, 20.0)) == 5  # its flanks are 15 m off the new edges: dropped
    assert len(simplify_ring(ring, 50.0)) == 4


def test_simplify_with_zero_tolerance_only_opens_the_ring():
    ring = _square(0, 0, 10, per_edge=3)
    out = simplify_ring(ring, 0)
    assert len(out) == len(ring) - 1 and not np.array_equal(out[0], out[-1])


def test_a_ring_smaller_than_the_tolerance_collapses():
    assert simplify_ring(_square(0, 0, 3), 10.0) is None


def test_to_feature_groups_holes_and_unprojects():
    x, y = STATCAN_LAMBERT.forward(-79.4, 43.7)
    outer = _square(x, y, 10_000, per_edge=10)
    hole = _square(x + 4000, y + 4000, 2000, clockwise=False)
    island = _square(x + 20_000, y, 5000)
    speck = _square(x + 40_000, y, 2)
    feature = to_feature([outer, hole, island, speck], 5.0, STATCAN_LAMBERT, "statcan:1")
    assert feature.id == "statcan:1"
    assert len(feature.outlines) == 2  # the speck is gone
    assert [len(o.rings) for o in feature.outlines] == [2, 1]
    assert [len(r) for r in feature.outlines[0].rings] == [4, 4]
    lat, lon = feature.outlines[0].rings[0][0]
    assert (lon, lat) == pytest.approx(STATCAN_LAMBERT.inverse(x, y), abs=1e-9)
    inside_hole = STATCAN_LAMBERT.inverse(x + 5000, y + 5000)
    in_ring = STATCAN_LAMBERT.inverse(x + 1000, y + 1000)
    assert not feature.contains(inside_hole[1], inside_hole[0])
    assert feature.contains(in_ring[1], in_ring[0])


def test_a_feature_smaller_than_the_tolerance_is_kept_unsimplified():
    x, y = STATCAN_LAMBERT.forward(-66.0, 45.0)
    feature = to_feature([_square(x, y, 3), _square(x + 10, y, 2)], 10.0, STATCAN_LAMBERT, "statcan:2")
    assert len(feature.outlines) == 1  # the larger ring survives, as drawn
    assert len(feature.outlines[0].rings[0]) == 4


def test_a_hole_outside_every_outer_ring_is_dropped():
    outer = _square(7_000_000, 900_000, 100)
    stray = _square(7_000_500, 900_000, 10, clockwise=False)
    feature = to_feature([outer, stray], 0, STATCAN_LAMBERT, "statcan:3")
    assert [len(o.rings) for o in feature.outlines] == [1]


def test_rings_without_any_clockwise_ring_are_all_outer():
    rings = [
        _square(7_000_000, 900_000, 100, clockwise=False),
        _square(7_000_500, 900_000, 100, clockwise=False),
    ]
    assert len(to_feature(rings, 0, STATCAN_LAMBERT, "x").outlines) == 2
