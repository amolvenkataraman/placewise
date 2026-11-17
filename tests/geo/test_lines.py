"""Line tools, against exact spherical geometry. Every test point is in open ocean (the equatorial
and North Atlantic), so none of them can be anybody's address."""

import math

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM as R
from placewise.geo import lines as ln

ONE_DEGREE_KM = R * math.pi / 180  # 111.195 km
ONE_DEGREE_M = ONE_DEGREE_KM * 1000
W = -20.0  # equatorial Atlantic: the equator from 20 W eastwards is open sea for hundreds of km


def _on_equator(*lons):
    return [(0.0, W + d) for d in lons]


# ---------------------------------------------------------------- simplify


@pytest.mark.parametrize("method", ["douglas_peucker", "visvalingam"])
def test_collinear_points_simplify_away(method):
    points = _on_equator(0, 1, 2, 3, 4, 5)
    assert list(ln.simplify(points, 1.0, method=method)) == [0, 5]


@pytest.mark.parametrize("method", ["douglas_peucker", "visvalingam"])
def test_simplify_always_keeps_both_ends_and_returns_int_indices(method):
    indices = ln.simplify(np.array(_on_equator(0, 1, 2)), 1e9, method=method)
    assert isinstance(indices, np.ndarray) and indices.dtype.kind == "i"
    assert list(indices) == [0, 2]
    assert list(ln.simplify(_on_equator(0, 1), 1e9, method=method)) == [0, 1]
    assert list(ln.simplify(_on_equator(0), 1e9, method=method)) == [0]
    assert list(ln.simplify([], 1.0, method=method)) == []


def test_douglas_peucker_keeps_a_spike_above_the_tolerance():
    # the spike is 0.01 deg = 1112 m off the chord; the points beside it are 556 m off their
    # chords to the spike
    points = [(0, W), (0, W + 1), (0.01, W + 2), (0, W + 3), (0, W + 4)]
    assert list(ln.simplify(points, 1000)) == [0, 2, 4]
    assert list(ln.simplify(points, 500)) == [0, 1, 2, 3, 4]
    assert list(ln.simplify(points, 0.01 * ONE_DEGREE_M + 50)) == [0, 4]


def test_simplify_tolerance_is_metres_not_degrees():
    # North Atlantic south of Iceland: a 0.01 deg step east at 60 N is only 0.01 * cos(60) deg of arc
    offset_m = 0.01 * ONE_DEGREE_M * math.cos(math.radians(60))  # 556 m
    points = [(59.9, W), (60.0, W + 0.01), (60.1, W)]
    assert list(ln.simplify(points, offset_m - 50)) == [0, 1, 2]
    assert list(ln.simplify(points, offset_m + 50)) == [0, 2]


def test_visvalingam_removes_the_smallest_area_first_and_recomputes_neighbours():
    # triangle areas in deg^2: P1 0.001, P2 0.0105, P3 0.02; once P1 goes, P2's triangle grows to 0.02
    points = [(0, W), (0.001, W + 1), (0, W + 2), (0.02, W + 3), (0, W + 4)]
    deg2 = ONE_DEGREE_M**2
    tol = math.sqrt(0.0125 * deg2)  # between P2's first area and its recomputed one
    # removing everything under the threshold at once would drop P2 as well
    assert list(ln.simplify(points, tol, method="visvalingam")) == [0, 2, 3, 4]
    below_all = math.sqrt(0.0009 * deg2)
    assert list(ln.simplify(points, below_all, method="visvalingam")) == [0, 1, 2, 3, 4]


def test_simplify_rejects_unknown_methods():
    with pytest.raises(ValueError):
        ln.simplify(_on_equator(0, 1, 2), 1.0, method="radial")


# ---------------------------------------------------------------- nearest point on a segment


def test_point_beside_the_middle_projects_to_fraction_half():
    lat, lon, dist, fraction = ln.nearest_point_on_segment(1.0, W + 1, (0, W), (0, W + 2))
    assert (lat, lon) == pytest.approx((0.0, W + 1), abs=1e-12)
    assert dist == pytest.approx(ONE_DEGREE_KM)  # 111.195 km
    assert dist == pytest.approx(111.195, abs=1e-3)
    assert fraction == pytest.approx(0.5)
    assert all(type(v) is float for v in (lat, lon, dist, fraction))


def test_points_beyond_the_ends_clamp_to_the_endpoints():
    a, b = (0, W), (0, W + 2)
    lat, lon, dist, fraction = ln.nearest_point_on_segment(1.0, W - 1, a, b)
    assert (lat, lon, fraction) == pytest.approx((0.0, W, 0.0), abs=1e-12)
    # spherical law of cosines from (1, -1) to (0, 0) relative to the start
    assert dist == pytest.approx(R * math.acos(math.cos(math.radians(1)) ** 2))
    lat, lon, dist, fraction = ln.nearest_point_on_segment(-0.5, W + 3, a, b)
    assert (lat, lon, fraction) == pytest.approx((0.0, W + 2, 1.0), abs=1e-12)
    assert dist == pytest.approx(R * math.acos(math.cos(math.radians(0.5)) * math.cos(math.radians(1))))


def test_projection_is_onto_the_great_circle_not_the_lat_lon_plane():
    # Atlantic west of Cape Verde. The foot of the perpendicular from (15 N, 1 deg east) to a
    # meridian is slightly poleward of 15 N: atan(tan 15 / cos 1)
    lat, lon, dist, fraction = ln.nearest_point_on_segment(15.0, -29.0, (10.0, -30.0), (20.0, -30.0))
    expected_lat = math.degrees(
        math.atan2(math.sin(math.radians(15)), math.cos(math.radians(15)) * math.cos(math.radians(1)))
    )
    assert lat == pytest.approx(expected_lat, abs=1e-10) and expected_lat > 15.001
    assert lon == pytest.approx(-30.0, abs=1e-10)
    assert dist == pytest.approx(R * math.asin(math.cos(math.radians(15)) * math.sin(math.radians(1))))
    assert fraction == pytest.approx((expected_lat - 10) / 10)


def test_nearest_point_on_segment_broadcasts_over_query_points():
    lats, lons = np.array([1.0, 1.0, -0.5]), np.array([W + 1, W - 1, W + 3])
    lat, lon, dist, fraction = ln.nearest_point_on_segment(lats, lons, (0, W), (0, W + 2))
    assert lat.shape == lon.shape == dist.shape == fraction.shape == (3,)
    np.testing.assert_allclose(fraction, [0.5, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(lon, [W + 1, W, W + 2], atol=1e-12)


def test_zero_length_segment_is_its_point():
    lat, lon, dist, fraction = ln.nearest_point_on_segment(1.0, W, (0, W), (0, W))
    assert (lat, lon, fraction) == pytest.approx((0.0, W, 0.0), abs=1e-12)
    assert dist == pytest.approx(ONE_DEGREE_KM)


# ---------------------------------------------------------------- nearest point on a polyline

L_SHAPE = [(0, W), (0, W + 2), (2, W + 2)]  # east along the equator, then north up a meridian


def test_nearest_point_on_polyline_picks_the_closest_segment():
    lat, lon, dist, index, fraction = ln.nearest_point_on_polyline(0.5, W + 0.5, L_SHAPE)
    assert (lat, lon) == pytest.approx((0.0, W + 0.5), abs=1e-12)
    assert dist == pytest.approx(0.5 * ONE_DEGREE_KM)
    assert index == 0 and type(index) is int
    assert fraction == pytest.approx(0.25)

    lat, lon, dist, index, fraction = ln.nearest_point_on_polyline(1.0, W + 3, L_SHAPE)
    expected_lat = math.degrees(math.atan2(math.sin(math.radians(1)), math.cos(math.radians(1)) ** 2))
    assert (lat, lon) == pytest.approx((expected_lat, W + 2), abs=1e-10)
    assert dist == pytest.approx(R * math.asin(math.cos(math.radians(1)) * math.sin(math.radians(1))))
    assert index == 1
    assert fraction == pytest.approx(expected_lat / 2)


def test_nearest_point_on_polyline_clamps_to_its_ends_and_vectorises():
    lats, lons = np.array([0.5, 1.0, 0.0, 3.0]), np.array([W + 0.5, W + 3, W - 1, W + 2])
    lat, lon, dist, index, fraction = ln.nearest_point_on_polyline(lats, lons, np.array(L_SHAPE))
    assert list(index) == [0, 1, 0, 1]
    np.testing.assert_allclose(fraction[2:], [0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(lat[2:], [0.0, 2.0], atol=1e-12)
    np.testing.assert_allclose(lon[2:], [W, W + 2], atol=1e-12)
    np.testing.assert_allclose(dist[2:], [ONE_DEGREE_KM, ONE_DEGREE_KM])


def test_nearest_point_on_polyline_needs_two_points():
    with pytest.raises(ValueError):
        ln.nearest_point_on_polyline(0.0, W, [(0, W)])


# ---------------------------------------------------------------- length


def test_polyline_length_sums_great_circle_legs():
    assert ln.polyline_length(_on_equator(0, 1, 3)) == pytest.approx(3 * ONE_DEGREE_KM)
    assert ln.polyline_length(np.array(L_SHAPE)) == pytest.approx(4 * ONE_DEGREE_KM)
    assert ln.polyline_length([(10.0, -30.0), (20.0, -30.0)]) == pytest.approx(10 * ONE_DEGREE_KM)


def test_polyline_length_of_fewer_than_two_points_is_zero():
    assert ln.polyline_length([]) == 0.0
    length = ln.polyline_length(_on_equator(0))
    assert length == 0.0 and type(length) is float
