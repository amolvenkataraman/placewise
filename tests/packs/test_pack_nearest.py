import numpy as np
import pytest
from pack_kit import CREATED, point_layer

from placewise.geo import haversine
from placewise.packs import open_pack, write_pack
from placewise.packs._points import PointGrid


def _open(tmp_path, lat, lon):
    lat, lon = np.round(np.asarray(lat, dtype=np.float64), 7), np.round(np.asarray(lon, dtype=np.float64), 7)
    path = write_pack(tmp_path, "test", "2026.11", [point_layer(lat, lon)], created=CREATED)
    return open_pack(path)["spots"], lat, lon


def _brute(lat, lon, qlat, qlon, k, max_km=None):
    d = haversine(qlat[:, None], qlon[:, None], lat[None, :], lon[None, :])
    order = np.argpartition(d, k - 1, axis=1)[:, :k]  # random data: no ties to break
    order = np.take_along_axis(order, np.argsort(np.take_along_axis(d, order, axis=1), axis=1), axis=1)
    dist = np.take_along_axis(d, order, axis=1)
    if max_km is not None:
        order = np.where(dist <= max_km, order, -1)
        dist = np.where(dist <= max_km, dist, np.inf)
    return order, dist


def _mixed_points(rng, n):
    """Uniform over the sphere plus tight clusters (cities are not uniform), some near the poles
    and the antimeridian."""
    u = n // 2
    lat = np.degrees(np.arcsin(rng.uniform(-1, 1, u)))
    lon = rng.uniform(-180, 180, u)
    centres = [(48.8, 2.3), (35.7, 139.7), (-17.5, 179.95), (89.5, 0.0), (-89.0, 45.0), (0.0, -179.99)]
    per = (n - u) // len(centres)
    for clat, clon in centres:
        lat = np.concatenate([lat, np.clip(clat + rng.normal(0, 0.3, per), -90, 90)])
        lon = np.concatenate([lon, (clon + rng.normal(0, 0.3, per) + 180) % 360 - 180])
    return lat, lon


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    rng = np.random.default_rng(11)
    lat, lon = _mixed_points(rng, 12_000)
    return _open(tmp_path_factory.mktemp("world"), lat, lon)


@pytest.mark.parametrize("k", [1, 5])
def test_nearest_equals_brute_force(world, k):
    layer, lat, lon = world
    rng = np.random.default_rng(12)
    qlat, qlon = _mixed_points(rng, 1000)
    idx, dist = layer.nearest(qlat, qlon, k=k)
    want_idx, want_dist = _brute(lat, lon, qlat, qlon, k)
    if k == 1:
        want_idx, want_dist = want_idx[:, 0], want_dist[:, 0]
    np.testing.assert_allclose(dist, want_dist, rtol=1e-12, atol=1e-9)
    np.testing.assert_array_equal(idx, want_idx)


def test_nearest_with_max_km(world):
    layer, lat, lon = world
    rng = np.random.default_rng(13)
    qlat, qlon = _mixed_points(rng, 1000)
    idx, dist = layer.nearest(qlat, qlon, k=3, max_km=50)
    want_idx, want_dist = _brute(lat, lon, qlat, qlon, 3, max_km=50)
    np.testing.assert_array_equal(idx, want_idx)
    np.testing.assert_allclose(dist, want_dist, rtol=1e-12, atol=1e-9)
    assert (idx == -1).any() and (idx >= 0).any()


@pytest.mark.parametrize("cell_deg", [0.05, 1.0, 10.0, 90.0])
def test_every_grid_size_gives_the_same_answers(cell_deg):
    rng = np.random.default_rng(15)
    lat, lon = _mixed_points(rng, 3000)
    qlat, qlon = _mixed_points(rng, 300)
    grid = PointGrid(lat, lon, cell_deg=cell_deg)
    idx, dist = grid.nearest(qlat, qlon, 3)
    want_idx, want_dist = _brute(lat, lon, qlat, qlon, 3)
    np.testing.assert_array_equal(idx, want_idx)
    np.testing.assert_allclose(dist, want_dist, rtol=1e-12, atol=1e-9)


def test_nearest_scalar_and_shapes(world):
    layer, lat, lon = world
    idx, dist = layer.nearest(48.85, 2.35)
    assert type(idx) is int and type(dist) is float
    assert dist == pytest.approx(haversine(48.85, 2.35, lat[idx], lon[idx]))
    idx, dist = layer.nearest(np.zeros((2, 3)), np.zeros((2, 3)), k=4)
    assert idx.shape == dist.shape == (2, 3, 4)
    idx, dist = layer.nearest(np.zeros((2, 3)), np.zeros((2, 3)))
    assert idx.shape == (2, 3)


def test_nearest_across_the_antimeridian_and_the_pole(tmp_path):
    layer, _, _ = _open(tmp_path, [0.0, 0.0, 89.9, 50.0], [179.99, -170.0, 0.0, 0.0])
    assert layer.nearest(0.0, -179.99)[0] == 0  # 2 km across the antimeridian, not 10 degrees west
    assert layer.nearest(89.9, 180.0)[0] == 2  # 22 km over the pole
    assert layer.nearest(89.9, 180.0)[1] == pytest.approx(haversine(89.9, 180.0, 89.9, 0.0))


def test_more_neighbours_than_points(tmp_path):
    layer, _, _ = _open(tmp_path, [0.0, 1.0], [0.0, 1.0])
    idx, dist = layer.nearest(0.0, 0.0, k=3)
    assert idx.tolist() == [0, 1, -1]
    assert dist[0] == 0 and dist[2] == np.inf


def test_within(world):
    layer, lat, lon = world
    rng = np.random.default_rng(14)
    qlat, qlon = _mixed_points(rng, 60)
    for a, b in zip(qlat, qlon, strict=True):
        for radius in (5.0, 80.0, 400.0):
            idx, dist = layer.within(a, b, radius)
            d = haversine(a, b, lat, lon)
            want = np.flatnonzero(d <= radius)
            want = want[np.argsort(d[want], kind="stable")]
            np.testing.assert_array_equal(idx, want)
            np.testing.assert_allclose(dist, d[want], rtol=1e-12)
