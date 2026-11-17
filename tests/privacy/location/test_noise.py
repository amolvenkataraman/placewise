"""Geo-indistinguishability: planar Laplace noise, seeded per place so repeats can't be averaged."""

import math

import numpy as np
import pytest
from privacy_kit import HOME, KEY, OTHER_KEY

from placewise.geo import haversine, initial_bearing
from placewise.privacy.location import geo_indistinguishable, radius_quantile

EPS = math.log(4) / 200  # Andrés et al.'s example: ln 4 of privacy within 200 m


def _spread_points(n_side=40, step_deg=0.05):
    # 2 km+ apart, so every point falls in its own noise cell and draws independent noise
    lat, lon = np.meshgrid(HOME[0] + np.arange(n_side) * step_deg, HOME[1] + np.arange(n_side) * step_deg)
    return lat.ravel(), lon.ravel()


def test_radius_quantile_inverts_the_gamma_2_cdf():
    p = np.r_[np.linspace(0.0, 0.999, 999), 1 - 1e-9]
    r = radius_quantile(p, EPS)
    x = EPS * r
    assert np.allclose(1 - (1 + x) * np.exp(-x), p, atol=1e-10)
    assert radius_quantile(0.0, EPS) == 0.0
    assert np.all(np.diff(r) > 0)
    assert type(radius_quantile(0.5, EPS)) is float


def test_displacements_follow_the_planar_laplacian():
    lat, lon = _spread_points()
    nlat, nlon = geo_indistinguishable(lat, lon, EPS, KEY)
    r = np.asarray(haversine(lat, lon, nlat, nlon)) * 1000
    assert r.mean() == pytest.approx(2 / EPS, rel=0.08)  # the Gamma(2, 1/ε) mean
    assert np.mean(r <= radius_quantile(0.5, EPS)) == pytest.approx(0.5, abs=0.04)
    assert np.mean(r <= radius_quantile(0.9, EPS)) == pytest.approx(0.9, abs=0.03)
    theta = np.radians(initial_bearing(lat, lon, nlat, nlon))
    assert np.hypot(np.cos(theta).mean(), np.sin(theta).mean()) < 0.06  # no preferred direction


def test_same_place_same_noise_so_repeats_cannot_be_averaged():
    lat = np.array([HOME[0], HOME[0], HOME[0] + 0.00001])  # last one ~1 m away: same noise cell
    lon = np.array([HOME[1], HOME[1], HOME[1]])
    a = geo_indistinguishable(lat, lon, EPS, KEY)
    b = geo_indistinguishable(lat, lon, EPS, KEY)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    assert a[0][0] == a[0][1] and a[1][0] == a[1][1]
    # the 1 m neighbour moves by the same displacement, so the mean of many releases is the
    # noisy point, not the true one
    assert a[0][2] - lat[2] == pytest.approx(a[0][0] - lat[0], abs=1e-9)
    assert a[1][2] - lon[2] == pytest.approx(a[1][0] - lon[0], abs=1e-9)


def test_key_separation_and_scalars():
    lat, lon = _spread_points(10)
    a = geo_indistinguishable(lat, lon, EPS, KEY)
    c = geo_indistinguishable(lat, lon, EPS, OTHER_KEY)
    assert np.all(a[0] != c[0])
    one = geo_indistinguishable(HOME[0], HOME[1], EPS, KEY)
    assert type(one[0]) is float and type(one[1]) is float
    assert one == (float(a[0][0]), float(a[1][0]))
    grid = geo_indistinguishable(np.zeros((2, 3)), np.full((2, 3), -20.0), EPS, KEY)
    assert grid[0].shape == (2, 3)


def test_smaller_epsilon_means_more_noise_and_bad_input_rejected():
    lat, lon = _spread_points(20)
    strong = geo_indistinguishable(lat, lon, EPS / 10, KEY)
    weak = geo_indistinguishable(lat, lon, EPS, KEY)
    assert np.asarray(haversine(lat, lon, *strong)).mean() > 5 * np.asarray(haversine(lat, lon, *weak)).mean()
    with pytest.raises(ValueError):
        geo_indistinguishable(0.0, 0.0, 0.0, KEY)
    with pytest.raises(ValueError):
        geo_indistinguishable(0.0, 0.0, EPS, b"")
    with pytest.raises(ValueError):
        radius_quantile(1.0, EPS)
