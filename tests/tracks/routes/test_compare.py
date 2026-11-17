"""Comparing tracks: Hausdorff and Fréchet distances, corridor overlap and deviations from a route.

Synthetic tracks sit on the equator near 20°W, in open ocean. There a great circle along the
equator is the equator itself and the distance from (lat, lon) to it is exactly |lat| in radians
times the Earth's radius, so the expected answers are exact.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.io import read_gpx
from placewise.tracks import Track
from placewise.tracks.routes import Overlap, deviations, frechet_km, hausdorff_km, overlap, same_route
from placewise.tracks.timing import resample

T0 = 1.7e9
DATA = Path(__file__).parents[2] / "data" / "tracks"


def _deg(km):
    """Degrees of arc for a distance along a great circle."""
    return math.degrees(km / MEAN_RADIUS_KM)


def _track(lat, lon, step_s=10.0):
    lat, lon = np.broadcast_arrays(np.asarray(lat, dtype=float), np.asarray(lon, dtype=float))
    return Track(T0 + np.arange(len(lat)) * step_s, lat, lon)


def _equator(lon0=-20.0, lon1=-19.9, n=101, lat=0.0):
    return _track(np.full(n, lat), np.linspace(lon0, lon1, n))


def _random_walk(rng, n):
    steps = rng.normal(0, 3e-4, size=(n, 2))
    pts = np.array([0.0, -20.0]) + rng.normal(0, 0.01, size=2) + np.cumsum(steps, axis=0)
    return _track(pts[:, 0], pts[:, 1])


# -- Hausdorff ----------------------------------------------------------------------------------


def test_hausdorff_of_parallel_meridians_one_km_apart():
    lat = np.linspace(0.0, 0.1, 50)
    a = _track(lat, -20.0)
    b = _track(lat, -20.0 + _deg(1.0))  # 1 km apart on the equator, converging slightly northwards
    assert hausdorff_km(a, b) == pytest.approx(1.0, abs=1e-9)
    assert hausdorff_km(b, a) == pytest.approx(1.0, abs=1e-9)
    assert hausdorff_km(a, a) == pytest.approx(0.0, abs=1e-9)


def test_hausdorff_measures_to_segments_not_just_fixes():
    sparse = _track([0.0, 0.0], [-20.0, -19.9])  # one 11 km leg
    dense = _equator()
    assert hausdorff_km(sparse, dense) == pytest.approx(0.0, abs=1e-9)
    # a point 300 m off the middle of the leg
    bump = _track([0.0, _deg(0.3), 0.0], [-20.0, -19.95, -19.9])
    assert hausdorff_km(sparse, bump) == pytest.approx(0.3, abs=1e-9)


def test_hausdorff_ignores_the_jump_across_a_segment_break():
    two = Track(T0 + np.arange(4.0), [0.0, 0.0, 0.0, 0.0], [-20.0, -19.99, -19.91, -19.9], segments=(0, 2))
    # the middle of the dense line is 0.04 degrees from the nearer end of a recorded piece
    expected = 0.04 * math.radians(MEAN_RADIUS_KM)
    assert hausdorff_km(two, _equator()) == pytest.approx(expected, rel=1e-9)


# -- Fréchet ------------------------------------------------------------------------------------


def test_frechet_of_parallel_lines_and_direction():
    a = _equator()
    b = _equator(lat=_deg(1.0))
    assert frechet_km(a, b) == pytest.approx(1.0, abs=1e-9)
    backwards = _track(a.lat[::-1], a.lon[::-1])
    assert hausdorff_km(a, backwards) == pytest.approx(0.0, abs=1e-9)
    assert frechet_km(a, backwards) == pytest.approx(0.1 * math.radians(MEAN_RADIUS_KM), rel=1e-9)


def test_frechet_is_at_least_hausdorff_on_random_pairs():
    rng = np.random.default_rng(7)
    for _ in range(20):
        a, b = _random_walk(rng, rng.integers(2, 150)), _random_walk(rng, rng.integers(2, 150))
        assert frechet_km(a, b) >= hausdorff_km(a, b) - 1e-12


def test_frechet_simplification_stays_close():
    a = _equator(n=1001)  # collinear: simplifies to its two ends
    b = _equator(n=1001, lat=_deg(0.2))
    assert frechet_km(a, b, simplify_m=5) == pytest.approx(0.2, abs=1e-9)


# -- overlap, same route, deviations ------------------------------------------------------------


def _l_route(lat0=0.0):
    """5.5 km east along the equator, then 5.5 km north."""
    lon = np.r_[np.linspace(-20.0, -19.95, 51), np.full(50, -19.95)]
    lat = np.r_[np.zeros(51), np.linspace(0.0, 0.05, 51)[1:]]
    return _track(lat + lat0, lon)


def test_overlap_with_itself_shifted_and_with_another_route():
    route = _l_route()
    shifted = _l_route(lat0=_deg(0.010))
    assert overlap(route, shifted) == Overlap(1.0, 1.0)
    assert same_route(route, shifted)

    crossing = _track(np.linspace(-0.05, 0.05, 101), -19.97)  # a meridian through the first leg
    a_in_b, b_in_a = overlap(route, crossing)
    length = 2 * 0.05 * math.radians(MEAN_RADIUS_KM)
    assert a_in_b == pytest.approx(0.060 / length, rel=1e-3)  # the 60 m within ±30 m of it
    assert b_in_a == pytest.approx(0.060 / length, rel=1e-3)
    assert not same_route(route, crossing)
    far = _l_route(lat0=1.0)
    assert overlap(route, far) == Overlap(0.0, 0.0)


def test_overlap_of_half_a_route():
    whole = _equator()
    half = _equator(lon1=-19.95, n=51)
    a_in_b, b_in_a = overlap(whole, half, corridor_m=30)
    # half the route plus the 30 m reaching past the end of the shorter one
    assert a_in_b == pytest.approx(0.5 + 0.030 / (0.1 * math.radians(MEAN_RADIUS_KM)), rel=1e-6)
    assert b_in_a == 1.0
    assert not same_route(whole, half)
    assert same_route(whole, half, min_overlap=0.5)


def test_deviations_find_one_detour():
    reference = _equator()
    lon = np.linspace(-20.0, -19.9, 101)
    # a 556 m detour north between -19.96 and -19.94 (fixes 40 .. 60), peaking at fix 50
    lat = np.where(np.abs(lon + 19.95) <= 0.01 + 1e-12, 0.005 * (1 - np.abs(lon + 19.95) / 0.01), 0.0)
    track = _track(lat, lon)
    found = deviations(track, reference, corridor_m=50)
    assert len(found) == 1
    d = found[0]
    assert d.max_distance_km == pytest.approx(0.005 * math.radians(MEAN_RADIUS_KM), rel=1e-9)
    assert (d.lat, d.lon) == (track.lat[50], track.lon[50])
    # the climb is linear in distance: 50 m off route 9 % of the way up from fix 40
    rise = 0.005 * math.radians(MEAN_RADIUS_KM) * 1000 / 10  # metres per fix
    assert d.first_index == 41 and d.last_index == 59
    assert d.start == pytest.approx(T0 + 400 + 10 * 50 / rise, abs=1e-6)
    assert d.end == pytest.approx(T0 + 600 - 10 * 50 / rise, abs=1e-6)
    assert deviations(reference, reference) == []


# -- realism ------------------------------------------------------------------------------------


def test_real_ride_against_itself_resampled_every_10_m():
    ride = read_gpx(DATA / "ttc_900_airport_express.gpx").tracks[0]
    every_10m = resample(ride, every_m=10)
    a_in_b, b_in_a = overlap(ride, every_10m)
    assert a_in_b == pytest.approx(1.0, abs=1e-3) and b_in_a == pytest.approx(1.0, abs=1e-3)
    assert hausdorff_km(ride, every_10m) < 0.010
    assert same_route(ride, every_10m)
