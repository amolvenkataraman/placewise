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


def _reference_simplify(ring, tolerance):
    """Ring-by-ring Douglas-Peucker with an explicit stack: what simplify_rings must reproduce."""
    pts = np.asarray(ring, dtype=np.float64)
    if len(pts) > 1 and np.array_equal(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    if tolerance <= 0:
        return pts
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
    if far == 0:
        return None

    def keep(line):
        mask = np.zeros(len(line), dtype=bool)
        mask[0] = mask[-1] = True
        stack = [(0, len(line) - 1)]
        while stack:
            i, j = stack.pop()
            if j - i < 2:
                continue
            a, b, between = line[i], line[j], line[i + 1 : j]
            dx, dy = b - a
            length = np.hypot(dx, dy)
            if length == 0:
                dist = np.hypot(*(between - a).T)
            else:
                dist = np.abs(dx * (between[:, 1] - a[1]) - dy * (between[:, 0] - a[0])) / length
            k = int(np.argmax(dist))
            if dist[k] > tolerance:
                k += i + 1
                mask[k] = True
                stack += [(i, k), (k, j)]
        return mask

    first, second = pts[: far + 1], np.vstack([pts[far:], pts[:1]])
    kept = np.vstack([first[keep(first)][:-1], second[keep(second)][:-1]])
    return kept if len(kept) >= 3 else None


def _random_rings(rng, count):
    rings = []
    for _ in range(count):
        n = int(rng.integers(3, 400))
        theta = np.sort(rng.uniform(0, 2 * np.pi, n))
        r = 1000 * (1 + 0.3 * np.sin(7 * theta) + 0.2 * rng.uniform(-1, 1, n))
        ring = np.column_stack([7e6 + r * np.cos(theta), 9e5 + r * np.sin(theta)])
        ring = np.round(ring, int(rng.integers(0, 3)))  # repeated and collinear vertices, ties
        if rng.uniform() < 0.3:
            ring = np.vstack([ring, ring[:1]])  # closed
        if rng.uniform() < 0.1:
            ring = np.vstack([ring[:2], ring[1:2], ring[1:]])  # a zero-length edge
        rings.append(ring)
    rings += [np.zeros((5, 2)), np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]), _square(0, 0, 3)]
    return rings


@pytest.mark.parametrize("tolerance", [0.0, 0.5, 10.0, 150.0])
def test_simplify_rings_matches_ring_by_ring_douglas_peucker(tolerance):
    from packbuild.polygons import simplify_rings

    rings = _random_rings(np.random.default_rng(int(tolerance * 10)), 300)
    for got, ring in zip(simplify_rings(rings, tolerance), rings, strict=True):
        want = _reference_simplify(ring, tolerance)
        assert (got is None) == (want is None)
        if want is not None:
            np.testing.assert_array_equal(got, want)


def test_to_features_matches_to_feature_one_at_a_time(monkeypatch):
    import packbuild.polygons as polygons

    rng = np.random.default_rng(5)
    x, y = STATCAN_LAMBERT.forward(-79.4, 43.7)
    records = []
    for k in range(40):
        outer = _square(x + 30_000 * k, y, 10_000, per_edge=int(rng.integers(1, 30)))
        hole = _square(x + 30_000 * k + 4000, y + 4000, 2000, per_edge=3, clockwise=False)
        records.append(([outer, hole, _square(x + 30_000 * k, y + 20_000, 4)], f"statcan:{k}"))
    one_by_one = [to_feature(rings, 5.0, STATCAN_LAMBERT, fid) for rings, fid in records]
    monkeypatch.setattr(polygons, "_BATCH_VERTICES", 500)  # several batches
    assert polygons.to_features(records, 5.0, STATCAN_LAMBERT) == one_by_one
