import math

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM as R
from placewise.geo import distances as d

ONE_DEGREE_KM = R * math.pi / 180


def test_haversine_exact_sphere_cases():
    assert d.haversine(0, 0, 0, 0) == 0
    assert d.haversine(0, 0, 0, 1) == pytest.approx(ONE_DEGREE_KM)
    assert d.haversine(0, 0, 90, 0) == pytest.approx(R * math.pi / 2)
    assert d.haversine(0, 0, 0, 180) == pytest.approx(R * math.pi)  # antipodal: acos formulas fail here


def test_haversine_across_the_antimeridian():
    assert d.haversine(0, 179.5, 0, -179.5) == pytest.approx(ONE_DEGREE_KM)


def test_scalars_give_floats_arrays_broadcast():
    assert type(d.haversine(0, 0, 0, 1)) is float
    one_to_many = d.haversine(0, 0, np.zeros(3), np.array([1, 2, 3]))
    np.testing.assert_allclose(one_to_many, ONE_DEGREE_KM * np.array([1, 2, 3]))
    pairwise = d.haversine(np.zeros(2), np.zeros(2), np.array([0, 90]), np.array([1, 0]))
    np.testing.assert_allclose(pairwise, [ONE_DEGREE_KM, R * math.pi / 2])


def test_haversine_custom_radius():
    assert d.haversine(0, 0, 0, 1, radius_km=1.0) == pytest.approx(math.pi / 180)


def test_equirectangular_matches_haversine_for_short_hops():
    lat, lon = 43.65, -79.38  # ~5 km hop at mid latitude
    exact = d.haversine(lat, lon, lat + 0.03, lon + 0.04)
    assert d.equirectangular(lat, lon, lat + 0.03, lon + 0.04) == pytest.approx(exact, rel=1e-5)


def test_equirectangular_across_the_antimeridian():
    assert d.equirectangular(10, 179.99, 10, -179.99) == pytest.approx(
        d.haversine(10, 179.99, 10, -179.99), rel=1e-6
    )


def test_geodesic_wgs84_reference_lengths():
    pytest.importorskip("geographiclib")
    assert d.geodesic(0, 0, 0, 1) == pytest.approx(6378.137 * math.pi / 180, abs=1e-9)  # along the equator
    assert d.geodesic(0, 0, 90, 0) == pytest.approx(10001.965729, abs=1e-6)  # equator to pole
    assert d.geodesic(0, 0, 0, 180) == pytest.approx(20003.931458, abs=1e-6)  # antipodal: over a pole


def test_geodesic_broadcasts():
    pytest.importorskip("geographiclib")
    out = d.geodesic(np.zeros(2), np.zeros(2), np.array([0, 90]), np.array([1, 0]))
    np.testing.assert_allclose(out, [6378.137 * math.pi / 180, 10001.965729], atol=1e-6)


def test_distance_picks_method_and_units():
    assert d.distance(0, 0, 0, 1) == d.haversine(0, 0, 0, 1)
    assert d.distance(0, 0, 0, 1, method="fast") == d.equirectangular(0, 0, 0, 1)
    assert d.distance(0, 0, 0, 1, units="mi") == pytest.approx(ONE_DEGREE_KM / 1.609344)
    with pytest.raises(ValueError, match="vincenty"):
        d.distance(0, 0, 0, 1, method="vincenty")
