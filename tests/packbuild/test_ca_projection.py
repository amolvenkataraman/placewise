"""Lambert Conformal Conic (2SP) maths, checked against published and authoritative control points."""

import itertools

import numpy as np
import pytest

from packbuild.projection import STATCAN_LAMBERT, LambertConformalConic

US_FOOT = 1200 / 3937


def test_iogp_guidance_note_7_2_worked_example():
    # IOGP Guidance Note 7-2, 3.2.1.1: NAD27 / Texas South Central (Clarke 1866, US survey feet)
    texas = LambertConformalConic(
        lat_origin=27 + 50 / 60,
        lon_origin=-99.0,
        lat_1=28 + 23 / 60,
        lat_2=30 + 17 / 60,
        false_easting=2_000_000 * US_FOOT,
        false_northing=0.0,
        a=6378206.400,
        inv_f=294.97870,
    )
    e, n = texas.forward(-96.0, 28.5)
    assert e / US_FOOT == pytest.approx(2963503.91, abs=0.02)
    assert n / US_FOOT == pytest.approx(254759.80, abs=0.02)
    lon, lat = texas.inverse(e, n)
    assert lon == pytest.approx(-96.0, abs=1e-10) and lat == pytest.approx(28.5, abs=1e-10)


# Boundary vertices of 2021 CSDs as Statistics Canada's own map service returns them, in EPSG:3347
# and, for the same vertex, in NAD83 lon/lat (EPSG:4269; geo.statcan.gc.ca, 2021 cartographic
# boundary files, layer 9, queried with outSR=3347 and outSR=4269, geometryPrecision=9).
STATCAN_CONTROL_POINTS = [
    # (CSD, x, y, lon, lat)
    ("St. John's", 8993058.462900005, 2130612.594300006, -52.737875577, 47.336009203),
    ("Gatineau", 7465758.437100008, 1195682.608600006, -75.748097816, 45.476924168),
    ("Toronto", 7220414.502900004, 925572.425700005, -79.442821136, 43.633777005),
    ("ID No. 9 Banff", 4541006.120000005, 2118359.740000006, -117.073328376, 52.221529435),
    ("Tofino", 3833426.134300005, 2091370.122900005, -125.905672759, 49.122177758),
    ("Iqaluit", 7293549.568600006, 3238757.371400006, -68.520976031, 63.721820995),
]


@pytest.mark.parametrize(("place", "x", "y", "lon", "lat"), STATCAN_CONTROL_POINTS)
def test_statcan_lambert_matches_statistics_canadas_own_reprojection(place, x, y, lon, lat):
    got_lon, got_lat = STATCAN_LAMBERT.inverse(x, y)
    assert got_lon == pytest.approx(lon, abs=1e-8), place  # ~1 mm; the service rounds to 1e-9°
    assert got_lat == pytest.approx(lat, abs=1e-8), place
    got_x, got_y = STATCAN_LAMBERT.forward(lon, lat)
    assert got_x == pytest.approx(x, abs=0.001) and got_y == pytest.approx(y, abs=0.001)


def test_epsg_3347_parameters():
    p = STATCAN_LAMBERT
    assert (p.lat_1, p.lat_2, p.lat_origin) == (49.0, 77.0, 63.390675)
    assert p.lon_origin == pytest.approx(-91.866667, abs=1e-6)  # 91°52'W
    assert (p.false_easting, p.false_northing) == (6200000.0, 3000000.0)
    assert (p.a, p.inv_f) == (6378137.0, 298.257222101)  # GRS 1980
    # the false origin maps to the false easting/northing
    assert p.forward(p.lon_origin, p.lat_origin) == pytest.approx((6200000.0, 3000000.0), abs=1e-6)


def test_arrays_round_trip_across_canada():
    lon = np.array([-141.0, -123.1, -79.38, -52.7, -62.3, -95.0])
    lat = np.array([60.0, 49.28, 43.65, 47.56, 82.5, 41.7])
    x, y = STATCAN_LAMBERT.forward(lon, lat)
    back_lon, back_lat = STATCAN_LAMBERT.inverse(x, y)
    np.testing.assert_allclose(back_lon, lon, atol=1e-10)
    np.testing.assert_allclose(back_lat, lat, atol=1e-10)
    assert STATCAN_LAMBERT.inverse(np.zeros(0), np.zeros(0))[0].shape == (0,)


def test_matches_pyproj_when_it_is_installed():
    pyproj = pytest.importorskip("pyproj")  # not a dependency; checked only where it happens to exist
    t = pyproj.Transformer.from_crs("EPSG:3347", "EPSG:4269", always_xy=True)
    x = np.array([p[1] for p in STATCAN_CONTROL_POINTS])
    y = np.array([p[2] for p in STATCAN_CONTROL_POINTS])
    want_lon, want_lat = t.transform(x, y)
    got_lon, got_lat = STATCAN_LAMBERT.inverse(x, y)
    np.testing.assert_allclose(got_lon, want_lon, atol=1e-9)
    np.testing.assert_allclose(got_lat, want_lat, atol=1e-9)


def test_inverse_rings_gives_the_numbers_of_ring_by_ring_inverse():
    rng = np.random.default_rng(3)
    sizes = rng.integers(0, 50, 200)
    x = rng.uniform(3.5e6, 9e6, sizes.sum())
    y = rng.uniform(0.5e6, 4.5e6, sizes.sum())
    offsets = np.concatenate([[0], np.cumsum(sizes)])
    lon, lat = STATCAN_LAMBERT.inverse_rings(x, y, offsets)
    for a, b in itertools.pairwise(offsets):
        want_lon, want_lat = STATCAN_LAMBERT.inverse(x[a:b], y[a:b])
        np.testing.assert_array_equal(lon[a:b], want_lon)
        np.testing.assert_array_equal(lat[a:b], want_lat)
