import math

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM as R
from placewise.geo import bearing as b
from placewise.geo.distances import haversine

ONE_DEGREE_KM = R * math.pi / 180


@pytest.mark.parametrize(("lat2", "lon2", "expected"), [(1, 0, 0), (0, 1, 90), (-1, 0, 180), (0, -1, 270)])
def test_initial_bearing_cardinal_directions(lat2, lon2, expected):
    assert b.initial_bearing(0, 0, lat2, lon2) == pytest.approx(expected)


def test_initial_bearing_is_in_0_360_and_crosses_antimeridian():
    assert b.initial_bearing(0, 179.5, 0, -179.5) == pytest.approx(90)
    assert 0 <= b.initial_bearing(10, 10, 5, 5) < 360


def test_final_bearing_is_reverse_initial_bearing_turned_around():
    # Toronto -> London: on a great circle the heading changes along the way
    final = b.final_bearing(43.65, -79.38, 51.51, -0.13)
    assert final == pytest.approx((b.initial_bearing(51.51, -0.13, 43.65, -79.38) + 180) % 360)
    assert abs(final - b.initial_bearing(43.65, -79.38, 51.51, -0.13)) > 30


def test_destination_known_points_and_wrap():
    assert b.destination(0, 0, 90, ONE_DEGREE_KM) == pytest.approx((0, 1))
    assert b.destination(0, 0, 0, R * math.pi / 2)[0] == pytest.approx(90)
    assert b.destination(0, 179.5, 90, ONE_DEGREE_KM) == pytest.approx((0, -179.5))


def test_destination_inverts_bearing_and_distance():
    lats1, lons1 = np.array([43.65, -33.87, 51.51]), np.array([-79.38, 151.21, -0.13])
    lats2, lons2 = np.array([12.97, 35.68, 40.71]), np.array([77.59, 139.69, -74.01])
    lat, lon = b.destination(
        lats1, lons1, b.initial_bearing(lats1, lons1, lats2, lons2), haversine(lats1, lons1, lats2, lons2)
    )
    np.testing.assert_allclose(lat, lats2, atol=1e-9)
    np.testing.assert_allclose(lon, lons2, atol=1e-9)


def test_midpoint_and_points_along_a_great_circle():
    assert b.midpoint(0, 0, 0, 90) == pytest.approx((0, 45))
    assert b.midpoint(0, 0, 90, 0) == pytest.approx((45, 0))
    lat, lon = b.along(0, 0, 0, 90, np.array([0, 0.5, 1]))
    np.testing.assert_allclose(lat, [0, 0, 0], atol=1e-12)
    np.testing.assert_allclose(lon, [0, 45, 90])


def test_cross_and_along_track_distance():
    # path eastward along the equator from (0, 0) to (0, 90)
    assert b.cross_track(0, 0, 0, 90, 0, 30) == pytest.approx(0, abs=1e-9)
    assert b.along_track(0, 0, 0, 90, 0, 30) == pytest.approx(30 * ONE_DEGREE_KM)
    left = b.cross_track(0, 0, 0, 90, 1, 45)  # north of an eastbound path is its left side
    assert left == pytest.approx(-ONE_DEGREE_KM)
    assert b.cross_track(0, 0, 0, 90, -1, 45) == pytest.approx(ONE_DEGREE_KM)


def test_compass_words():
    assert [b.compass(x) for x in (0, 44, 90, 200, 359)] == ["N", "NE", "E", "S", "N"]
    assert b.compass(22.6, points=16) == "NNE"
    assert list(b.compass(np.array([0, 180]))) == ["N", "S"]
    with pytest.raises(ValueError):
        b.compass(10, points=12)
