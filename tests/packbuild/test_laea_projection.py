"""Lambert Azimuthal Equal Area (EPSG method 9820), checked against the IOGP worked example."""

import numpy as np
import pytest

from packbuild.projection import ETRS89_LAEA, LambertAzimuthalEqualArea


def test_iogp_guidance_note_7_2_worked_example():
    # IOGP Guidance Note 7-2, 3.3.2: ETRS89 / ETRS-LAEA (EPSG:3035), 50°N 5°E
    e, n = ETRS89_LAEA.forward(5.0, 50.0)
    assert e == pytest.approx(3962799.45, abs=0.01)
    assert n == pytest.approx(2999718.85, abs=0.01)
    lon, lat = ETRS89_LAEA.inverse(3962799.45, 2999718.85)
    assert lon == pytest.approx(5.0, abs=1e-7)  # ~1 cm: the example's E and N are rounded to 1 cm
    assert lat == pytest.approx(50.0, abs=1e-7)


def test_etrs89_laea_parameters():
    # EPSG:3035: latitude of natural origin 52°N, longitude 10°E, FE 4 321 000 m, FN 3 210 000 m, GRS 1980
    assert (ETRS89_LAEA.lat_origin, ETRS89_LAEA.lon_origin) == (52.0, 10.0)
    assert (ETRS89_LAEA.false_easting, ETRS89_LAEA.false_northing) == (4321000.0, 3210000.0)
    lon, lat = ETRS89_LAEA.inverse(4321000.0, 3210000.0)
    assert float(lon) == 10.0  # the origin (its latitude through the series: under 1 mm)
    assert float(lat) == pytest.approx(52.0, abs=1e-8)


def test_round_trip_across_europe_is_within_millimetres():
    rng = np.random.default_rng(7)
    lon = rng.uniform(-31.0, 45.0, 5000)  # the Azores to the Caucasus
    lat = rng.uniform(27.0, 81.0, 5000)  # the Canaries to Svalbard
    x, y = ETRS89_LAEA.forward(lon, lat)
    back_lon, back_lat = ETRS89_LAEA.inverse(x, y)
    # the inverse latitude is GN 7-2's series to e^6, good to a couple of millimetres (1e-8° ~ 1 mm)
    assert np.abs(back_lon - lon).max() < 1e-9
    assert np.abs(back_lat - lat).max() < 2e-8


def test_arrays_and_scalars_agree():
    x = np.array([3962799.45, 4321000.0, 3000000.0])
    y = np.array([2999718.85, 3210000.0, 2000000.0])
    lon, lat = ETRS89_LAEA.inverse(x, y)
    for k in range(3):
        one = ETRS89_LAEA.inverse(x[k], y[k])
        assert (float(lon[k]), float(lat[k])) == (float(one[0]), float(one[1]))


def test_a_sphere_has_the_spherical_formulas():
    # on a sphere (inv_f = inf) the authalic latitude is the latitude: Snyder (1987) 24-2, 24-3
    sphere = LambertAzimuthalEqualArea(lat_origin=0.0, lon_origin=0.0, a=1.0, inv_f=float("inf"))
    x, y = sphere.forward(90.0, 0.0)  # a quarter round the equator: k' = sqrt(2)
    assert (float(x), float(y)) == pytest.approx((np.sqrt(2.0), 0.0), abs=1e-12)
    lon, lat = sphere.inverse(x, y)
    assert (float(lon), float(lat)) == pytest.approx((90.0, 0.0), abs=1e-10)


# Boundary vertices of nationally designated areas as the EEA's own map service returns them, in
# EPSG:3035 and, for the same vertex, in WGS 84 (bio.discomap.eea.europa.eu, ProtectedSites/
# NatDAv23_Dyna_LAEA, layer 4, queried with outSR=3035 and outSR=4326, geometryPrecision=9)
EEA_CONTROL_POINTS = [
    # (site, x, y, lon, lat)
    ("České Švýcarsko", 4630240.2705, 3101930.2263, 14.403041872, 50.944963841),
    ("Plitvička jezera", 4764910.8377, 2420256.6829, 15.600626982, 44.743818873),
    ("Peneda-Geres", 2818959.5272, 2257444.3151, -8.197942013, 41.777910348),
    ("Lemmenjoen kansallispuisto", 4956622.1501, 5095950.7198, 25.419841676, 68.344341399),
    ("Ecrins", 4003122.1784, 2438543.4303, 5.974513013, 44.98144213),
    ("Dadia - Lefkimi - Soufli", 5669687.5019, 2133633.2022, 26.097625848, 41.003864647),
]


@pytest.mark.parametrize(("site", "x", "y", "lon", "lat"), EEA_CONTROL_POINTS)
def test_etrs89_laea_matches_the_eeas_own_reprojection(site, x, y, lon, lat):
    got_lon, got_lat = ETRS89_LAEA.inverse(x, y)
    assert float(got_lon) == pytest.approx(lon, abs=1e-8), site  # ~1 mm; the service rounds to 1e-9°
    assert float(got_lat) == pytest.approx(lat, abs=1e-8), site
