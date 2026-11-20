import math

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM as R
from placewise.geo import shapes as s

ONE_DEGREE_KM = R * math.pi / 180
SQUARE = [(0, 0), (0, 10), (10, 10), (10, 0)]  # (lat, lon) ring


def test_bbox_around_at_the_equator():
    assert s.bbox_around(0, 0, ONE_DEGREE_KM) == pytest.approx((-1, -1, 1, 1))


def test_bbox_around_widens_in_longitude_away_from_the_equator():
    south, west, north, east = s.bbox_around(60, 0, ONE_DEGREE_KM)
    assert (south, north) == pytest.approx((59, 61))
    # exact half-width of a spherical cap: asin(sin(r) / cos(lat))
    assert east == pytest.approx(math.degrees(math.asin(math.sin(math.radians(1)) / 0.5)))
    assert west == pytest.approx(-east)


def test_bbox_around_crossing_the_antimeridian_has_west_greater_than_east():
    south, west, north, east = s.bbox_around(0, 179.5, ONE_DEGREE_KM)
    assert (west, east) == pytest.approx((178.5, -179.5))
    east_part, west_part = s.bbox_split((south, west, north, east))
    assert east_part == pytest.approx((south, 178.5, north, 180.0))
    assert west_part == pytest.approx((south, -180.0, north, -179.5))


def test_bbox_around_a_pole_spans_all_longitudes():
    assert s.bbox_around(89.5, 20, ONE_DEGREE_KM) == pytest.approx((88.5, -180, 90, 180))


def test_bbox_contains_handles_antimeridian_boxes():
    box = (-1, 178.5, 1, -179.5)
    inside = s.bbox_contains(box, np.array([0, 0, 0, 5]), np.array([179, -179.9, 0, 179]))
    assert list(inside) == [True, True, False, False]


def test_contains_square_concave_and_hole():
    lats, lons = np.array([5, 15, 5, -1]), np.array([5, 5, 11, 5])
    assert list(s.contains([SQUARE], lats, lons)) == [True, False, False, False]
    l_shape = [(0, 0), (0, 10), (5, 10), (5, 5), (10, 5), (10, 0)]
    assert list(s.contains([l_shape], np.array([2, 8, 8]), np.array([8, 2, 8]))) == [True, True, False]
    with_hole = [SQUARE, [(4, 4), (4, 6), (6, 6), (6, 4)]]
    assert list(s.contains(with_hole, np.array([5, 2]), np.array([5, 2]))) == [False, True]
    assert s.contains([SQUARE], 5, 5) is True


def test_area_of_the_octant_triangle_is_exact():
    # three right angles: one eighth of the sphere
    assert s.area([[(0, 0), (0, 90), (90, 0)]]) == pytest.approx(4 * math.pi * R**2 / 8)


def test_area_of_a_one_degree_cell_matches_closed_form():
    expected = R**2 * math.radians(1) * math.sin(math.radians(1))  # parallels-bounded cell
    assert s.area([[(0, 0), (0, 1), (1, 1), (1, 0)]]) == pytest.approx(expected, rel=1e-4)


def test_area_ignores_winding_and_subtracts_holes():
    cell = [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert s.area([cell[::-1]]) == pytest.approx(s.area([cell]))
    hole = [(0.25, 0.25), (0.25, 0.75), (0.75, 0.75), (0.75, 0.25)]
    assert s.area([cell, hole]) == pytest.approx(s.area([cell]) - s.area([hole]))


# --- nesting rings into polygons (GeoJSON output) ----------------------------------------------

HOLE = [(4, 4), (4, 6), (6, 6), (6, 4)]
ISLAND = [(4.5, 4.5), (4.5, 5.5), (5.5, 5.5), (5.5, 4.5)]  # inside HOLE: a polygon of its own
APART = [(20, 20), (20, 22), (22, 22), (22, 20)]


def test_nest_puts_each_hole_under_its_ring():
    assert s.nest([SQUARE, HOLE]) == [[0, 1]]
    assert s.nest([HOLE, SQUARE]) == [[1, 0]]  # order of the rings doesn't matter
    assert s.nest([SQUARE, APART, HOLE]) == [[0, 2], [1]]


def test_nest_an_island_in_a_lake_is_a_polygon_again():
    assert s.nest([SQUARE, HOLE, ISLAND]) == [[0, 1], [2]]


def test_nest_rings_touching_at_a_corner_still_nest():
    corner = [(0, 0), (0, 3), (3, 3), (3, 0)]  # shares the outer ring's corner
    assert s.nest([SQUARE, corner]) == [[0, 1]]


def test_planar_signed_area_is_positive_counter_clockwise_on_a_map():
    ccw = [(0, 0), (0, 10), (10, 10), (10, 0)]  # (lat, lon): east, north, west: counter-clockwise
    assert s.planar_signed_area(ccw) == pytest.approx(100.0)
    assert s.planar_signed_area(ccw[::-1]) == pytest.approx(-100.0)
    assert s.planar_signed_area([*ccw, ccw[0]]) == pytest.approx(100.0)  # closed rings too
