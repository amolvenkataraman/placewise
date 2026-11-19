"""Mollweide on a sphere (packbuild.projection.Mollweide), against Snyder's worked example and the
projection's own geometry."""

import math

import numpy as np
import pytest

from packbuild.projection import WORLD_MOLLWEIDE, Mollweide

R = 6378137.0


def test_auxiliary_angle_and_meridians():
    # Snyder, Map Projections: A Working Manual (1987), pp. 249-252: y = sqrt(2) R sin(theta) with
    # 2 theta + sin(2 theta) = pi sin(lat); x = 2 sqrt(2) / pi R (lon - lon0) cos(theta); here R = 1
    unit = Mollweide(radius=1.0, lon_origin=-90.0)
    lat = np.array([-35.0, 0.0, 12.5, 60.0, 89.0])
    x, y = unit.forward(np.full(5, -102.0), lat)
    theta = np.arcsin(y / math.sqrt(2))
    assert 2 * theta + np.sin(2 * theta) == pytest.approx(np.pi * np.sin(np.radians(lat)), abs=1e-12)
    assert x == pytest.approx(2 * math.sqrt(2) / math.pi * math.radians(-12.0) * np.cos(theta), abs=1e-12)
    # the meridians 180 degrees from the centre form the bounding ellipse
    x, y = unit.forward(np.full(5, 90.0), lat)
    assert (x / (2 * math.sqrt(2))) ** 2 + (y / math.sqrt(2)) ** 2 == pytest.approx(np.ones(5), abs=1e-12)
    lon, back = unit.inverse(x, y)
    assert lon == pytest.approx(np.full(5, 90.0), abs=1e-9) and back == pytest.approx(lat, abs=1e-9)


def test_ellipse_extremes():
    x, y = WORLD_MOLLWEIDE.forward(np.array([180.0, -180.0, 0.0, 0.0]), np.array([0.0, 0.0, 90.0, -90.0]))
    assert x == pytest.approx([2 * math.sqrt(2) * R, -2 * math.sqrt(2) * R, 0, 0], abs=1e-6)
    assert y == pytest.approx([0, 0, math.sqrt(2) * R, -math.sqrt(2) * R], abs=1e-6)
    lon, lat = WORLD_MOLLWEIDE.inverse(0.0, math.sqrt(2) * R)
    assert lat == pytest.approx(90.0) and lon == pytest.approx(0.0)


def test_round_trip_over_the_globe():
    rng = np.random.default_rng(7)
    lon, lat = rng.uniform(-180, 180, 20_000), rng.uniform(-89.9, 89.9, 20_000)
    x, y = WORLD_MOLLWEIDE.forward(lon, lat)
    back_lon, back_lat = WORLD_MOLLWEIDE.inverse(x, y)
    assert np.abs(back_lat - lat).max() < 1e-9 and np.abs(back_lon - lon).max() < 1e-9


def test_equal_area():
    # a 1 x 1 degree box at the equator and at 60 N: projected areas match the sphere's
    for lat0 in (0.0, 60.0):
        lon = np.array([10.0, 11.0, 11.0, 10.0])
        lat = np.array([lat0, lat0, lat0 + 1, lat0 + 1])
        x, y = WORLD_MOLLWEIDE.forward(lon, lat)
        area = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))
        sphere = R**2 * math.radians(1.0) * (math.sin(math.radians(lat0 + 1)) - math.sin(math.radians(lat0)))
        assert area == pytest.approx(sphere, rel=2e-4)  # straight edges cut the curved parallels


def test_outside_the_ellipse_is_clipped():
    lon, lat = WORLD_MOLLWEIDE.inverse(18_041_000.0, 0.0)  # the GHSL grid's west edge, mirrored
    assert lon == 180.0 and lat == 0.0
