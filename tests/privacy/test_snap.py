"""Keyed grid snapping: secret grid origin, roughly square metric cells, vectorised."""

import numpy as np
import pytest
from privacy_synth import HOME, KEY, OTHER_KEY, distance_m

from placewise.geo import haversine
from placewise.privacy.snap import keyed_snap


def _cloud(n=2000, spread_deg=0.05, seed=0):
    rng = np.random.default_rng(seed)
    return HOME[0] + rng.uniform(-spread_deg, spread_deg, n), HOME[1] + rng.uniform(
        -spread_deg, spread_deg, n
    )


def test_scalars_in_floats_out_and_shapes_kept():
    lat, lon = keyed_snap(0.001, -20.001, 100.0, KEY)
    assert type(lat) is float and type(lon) is float
    grid_lat, grid_lon = keyed_snap(np.zeros((3, 4)), np.full((3, 4), -20.0), 100.0, KEY)
    assert grid_lat.shape == grid_lon.shape == (3, 4)


def test_snapped_points_stay_within_half_a_cell_diagonal():
    lat, lon = _cloud()
    for cell in (25.0, 100.0, 1000.0):
        slat, slon = keyed_snap(lat, lon, cell, KEY)
        moved = np.asarray(haversine(lat, lon, slat, slon)) * 1000
        assert moved.max() <= cell * np.sqrt(2) / 2 * 1.01
        assert moved.mean() > cell * 0.2  # it did snap


def test_cells_are_roughly_square_metres_even_away_from_the_equator():
    for lat0 in (0.0, 60.0, -45.0):
        # rows: centre latitudes one cell apart (each row has its own secret longitude offset, so
        # only the north-south component is compared)
        north_lat, _ = keyed_snap(np.linspace(lat0, lat0 + 0.02, 2000), np.full(2000, -20.0), 100.0, KEY)
        rows = np.unique(north_lat)
        assert np.allclose(np.diff(rows) * 111_195.0, 100.0, rtol=0.01)
        # within a row: neighbouring centres one cell apart on the ground
        east_lat, east_lon = keyed_snap(np.full(2000, lat0), np.linspace(-20.0, -19.96, 2000), 100.0, KEY)
        assert len(np.unique(east_lat)) == 1
        lons = np.unique(east_lon)
        steps = np.asarray(haversine(east_lat[0], lons[:-1], east_lat[0], lons[1:])) * 1000
        assert np.allclose(steps, 100.0, rtol=0.01), (lat0, steps.min(), steps.max())


def test_idempotent_and_shared_centres():
    lat, lon = _cloud()
    slat, slon = keyed_snap(lat, lon, 100.0, KEY)
    again = keyed_snap(slat, slon, 100.0, KEY)
    assert np.allclose(again[0], slat, atol=1e-12) and np.allclose(again[1], slon, atol=1e-12)
    assert len(np.unique(np.c_[slat, slon], axis=0)) < len(lat)  # many points per cell


def test_deterministic_and_key_separated():
    lat, lon = _cloud()
    a = keyed_snap(lat, lon, 100.0, KEY)
    b = keyed_snap(lat, lon, 100.0, KEY)
    c = keyed_snap(lat, lon, 100.0, OTHER_KEY)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    assert np.mean(distance_m(a[0], a[1], (0, 0)) != distance_m(c[0], c[1], (0, 0))) > 0.99


def test_grid_origin_is_secret_not_aligned_to_round_coordinates():
    # an unkeyed grid would put a cell boundary (or centre) at a predictable place such as the
    # equator; across keys the snapped latitude of one point must spread over the whole cell
    snapped = [keyed_snap(0.0, -20.0, 100.0, f"origin-key-{i:03d}".encode() * 2)[0] for i in range(200)]
    cell_deg = 100.0 / 111_195.0
    assert np.ptp(snapped) > 0.8 * cell_deg


def test_antimeridian_poles_and_bad_cells():
    lat, lon = keyed_snap(
        np.array([10.0, 10.0, 89.9999, -90.0]), np.array([179.9999, -180.0, 5.0, 0.0]), 100.0, KEY
    )
    assert np.all(np.abs(lat) <= 90) and np.all((lon >= -180) & (lon < 180))
    with pytest.raises(ValueError):
        keyed_snap(0.0, 0.0, 0.0, KEY)
    with pytest.raises(ValueError):
        keyed_snap(0.0, 0.0, 100.0, b"")
