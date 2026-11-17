"""Distances to polygon boundaries: near_boundary and nearest_boundary against the brute force of
nearest_edge_km over every feature (exact great-circle distance to every edge)."""

import numpy as np
import pytest
from pack_kit import CREATED, blob_features, box_feature, fiji, polygon_layer

from placewise.geo import haversine
from placewise.packs import open_pack, write_pack


def _open(tmp_path, features, cell_deg=1.0):
    path = write_pack(
        tmp_path, "test", "2026.11", [polygon_layer(features, cell_deg=cell_deg)], created=CREATED
    )
    return open_pack(path)["areas"]


def _layers():
    rng = np.random.default_rng(51)
    return {
        "blobs": blob_features(30, rng, radius=(0.3, 3.0), lat_range=(-30, 30)),
        "holes_and_islands": blob_features(25, rng, radius=(1.0, 4.0), holes=True),
        # long edges far north (arcs bulge from straight lines in lat/lon), Fiji split at ±180
        "polar_and_antimeridian": [
            fiji(),
            box_feature(70, -40, 84, 40),
            box_feature(-85, -170, -78, -10),
            *blob_features(8, rng, lat_range=(-60, 60)),
        ],
    }


LAYERS = _layers()


def _points(layer, features, rng, n):
    """Near the features' edges (vertices nudged a little), plus anywhere."""
    vertices = np.array([v for f in features for o in f.outlines for r in o.rings for v in r])
    pick = vertices[rng.integers(0, len(vertices), n // 2)]
    near_lat = np.clip(pick[:, 0] + rng.normal(0, 0.3, n // 2), -90, 90)
    near_lon = (pick[:, 1] + rng.normal(0, 0.3, n // 2) + 180) % 360 - 180
    lat = np.concatenate([near_lat, np.degrees(np.arcsin(rng.uniform(-1, 1, n - n // 2)))])
    lon = np.concatenate([near_lon, rng.uniform(-180, 180, n - n // 2)])
    return lat, lon


def _brute(layer, lat, lon):
    """(points, features) km from each point to each feature's boundary."""
    return np.array([layer.nearest_edge_km(lat, lon, f) for f in range(layer.count)]).T


@pytest.mark.parametrize("kind", list(LAYERS))
@pytest.mark.parametrize("radius_km", [0.0, 22.2, 150.0])
def test_near_boundary_equals_brute_force(tmp_path, kind, radius_km):
    layer = _open(tmp_path, LAYERS[kind])
    lat, lon = _points(layer, LAYERS[kind], np.random.default_rng(52), 400)
    km = _brute(layer, lat, lon)
    point, feature, dist = layer.near_boundary(lat, lon, radius_km)
    want_p, want_f = np.nonzero(km <= radius_km)  # row-major: by point, then feature
    np.testing.assert_array_equal(point, want_p)
    np.testing.assert_array_equal(feature, want_f)
    np.testing.assert_allclose(dist, km[want_p, want_f], rtol=1e-9, atol=1e-9)
    if radius_km:
        assert len(point) > 20  # the comparison means something


@pytest.mark.parametrize("kind", list(LAYERS))
def test_nearest_boundary_equals_brute_force(tmp_path, kind):
    layer = _open(tmp_path, LAYERS[kind], cell_deg=0.5)
    lat, lon = _points(layer, LAYERS[kind], np.random.default_rng(53), 300)
    km = _brute(layer, lat, lon)
    for max_km in (None, 400.0):
        feature, dist, at_lat, at_lon = layer.nearest_boundary(lat, lon, max_km=max_km)
        want_f = np.argmin(km, axis=1)  # ties to the lower index
        want_d = km[np.arange(len(lat)), want_f]
        if max_km is not None:
            far = want_d > max_km
            want_f, want_d = np.where(far, -1, want_f), np.where(far, np.inf, want_d)
            assert far.any() and not far.all()
        np.testing.assert_array_equal(feature, want_f)
        np.testing.assert_allclose(dist, want_d, rtol=1e-9, atol=1e-9)
        found = feature >= 0
        # the nearest boundary point is that far away, and NaN where there is none
        np.testing.assert_allclose(
            haversine(lat, lon, at_lat, at_lon)[found], dist[found], rtol=1e-6, atol=1e-6
        )
        assert np.isnan(at_lat[~found]).all() and np.isnan(at_lon[~found]).all()


@pytest.mark.parametrize("kind", list(LAYERS))
def test_nearest_edge_km_equals_measuring_every_edge(tmp_path, kind):
    """Measuring only the runs of edges whose caps can hold the nearest gives the very same numbers
    as measuring every edge, bit for bit, for points near the edges, anywhere, and at the poles."""
    layer = _open(tmp_path, LAYERS[kind])
    lat, lon = _points(layer, LAYERS[kind], np.random.default_rng(54), 300)
    lat, lon = np.append(lat, [90.0, -90.0, 0.0, -17.5]), np.append(lon, [0.0, 45.0, 180.0, -180.0])
    for f in range(layer.count):
        got = layer.nearest_edge_km(lat, lon, f)
        np.testing.assert_array_equal(got, layer._every_edge_km(lat, lon, f))
        assert np.isfinite(got).all()


def test_nearest_edge_km_odd_input(tmp_path):
    layer = _open(tmp_path, [box_feature(0, 0, 10, 10, (4, 4, 6, 6)), fiji()])
    got = layer.nearest_edge_km([np.nan, 5.0, 5.0, 95.0], [0.0, np.inf, 365.0, 5.0], 0)
    assert np.isinf(got[:2]).all()
    assert got[2] == pytest.approx(111.2, rel=1e-2)  # 365 is 5 degrees east
    assert np.isfinite(got[3])
    assert layer.nearest_edge_km(5.0, 5.0, 0) == pytest.approx(111.2, rel=1e-2)
    assert layer.nearest_edge_km(np.zeros((2, 3)), np.zeros((2, 3)), 0).shape == (2, 3)


def test_boundary_queries_shapes_and_odd_input(tmp_path):
    layer = _open(tmp_path, [box_feature(0, 0, 10, 10, (4, 4, 6, 6)), fiji()])
    point, feature, dist = layer.near_boundary([5.0, 2.0, np.nan, 95.0], [5.0, 2.0, 0.0, 0.0], 250.0)
    assert point.tolist() == [0, 1] and feature.tolist() == [0, 0]  # the hole's edge; the outer edge
    assert dist[0] == pytest.approx(111.2, rel=1e-2) and dist[1] == pytest.approx(222.3, rel=1e-2)
    assert point.dtype == feature.dtype == np.int64
    empty = layer.near_boundary(np.array([]), np.array([]), 50.0)
    assert [len(a) for a in empty] == [0, 0, 0]
    # the antimeridian cut is not a border: 0.1 degree from it, Fiji's real edges are 1.5 away
    assert len(layer.near_boundary(-17.5, 179.9, 50.0)[0]) == 0
    f, d, _, _ = layer.nearest_boundary(-17.5, 179.9)
    assert f == 1 and d == pytest.approx(1.5 * 111.195, rel=1e-2) and type(f) is int and type(d) is float
    f, d, a, _ = layer.nearest_boundary(np.nan, 0.0)
    assert f == -1 and d == np.inf and np.isnan(a)
