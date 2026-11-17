import time
import tracemalloc

import numpy as np
import pytest
from pack_kit import CREATED, point_layer

from placewise.geo import haversine
from placewise.packs import PointIndex, open_pack, write_pack


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


def _brute_ties(lat, lon, qlat, qlon, k):
    """k nearest by brute force, equal distances to the lower index."""
    d = haversine(qlat[:, None], qlon[:, None], lat[None, :], lon[None, :])
    order = np.array([np.lexsort((np.arange(len(lat)), row))[:k] for row in d])
    return order, np.take_along_axis(d, order, axis=1)


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
    index = PointIndex(lat, lon, cell_deg=cell_deg)
    idx, dist = index.nearest(qlat, qlon, k=3)
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


def test_point_index_is_the_layers_search(world):
    """The public index over the same points answers exactly as the layer, which uses it."""
    layer, lat, lon = world
    index = PointIndex(lat, lon)
    assert len(index) == len(lat) and index.cell_deg > 0
    np.testing.assert_array_equal(index.lat, lat)
    rng = np.random.default_rng(16)
    qlat, qlon = _mixed_points(rng, 500)
    for k, max_km in ((1, None), (4, None), (3, 80.0)):
        got, want = (
            index.nearest(qlat, qlon, k=k, max_km=max_km),
            layer.nearest(qlat, qlon, k=k, max_km=max_km),
        )
        np.testing.assert_array_equal(got[0], want[0])
        np.testing.assert_array_equal(got[1], want[1])
    i, d = index.nearest(48.85, 2.35)
    assert type(i) is int and type(d) is float and (i, d) == layer.nearest(48.85, 2.35)
    assert index.nearest(np.zeros((2, 3)), np.zeros((2, 3)), k=2)[0].shape == (2, 3, 2)
    assert index.nearest(0.0, 360.0) == index.nearest(0.0, 0.0)  # longitudes wrap
    assert index.nearest(np.nan, 0.0) == (-1, np.inf)
    for got, want in zip(index.within(48.85, 2.35, 120.0), layer.within(48.85, 2.35, 120.0), strict=True):
        np.testing.assert_array_equal(got, want)


def test_point_index_edge_cases():
    empty = PointIndex(np.zeros(0), np.zeros(0))
    assert empty.nearest(1.0, 2.0) == (-1, np.inf)
    assert len(empty.within(1.0, 2.0, 100.0)[0]) == 0
    index = PointIndex([10.0, 10.0, -30.0], [20.0, 20.0, 150.0])  # a duplicate point
    idx, dist = index.nearest(10.0, 20.0, k=3)
    assert idx.tolist() == [0, 1, 2] and dist[0] == dist[1] == 0  # ties go to the lower index
    assert index.nearest(10.0, 20.0, k=2, max_km=0.0)[0].tolist() == [0, 1]
    # many equal distances, more than k of them, for both ways of picking the k best
    rng = np.random.default_rng(17)
    lat = np.where(rng.uniform(size=300) < 0.5, 5.0, rng.uniform(4, 6, 300))
    lon = np.where(lat == 5.0, 5.0, rng.uniform(4, 6, 300))
    tied = PointIndex(lat, lon)
    for k in (5, 12, 40):
        idx, dist = tied.nearest([5.0, 5.0001], [5.0, 5.0], k=k)
        want_idx, want_dist = _brute_ties(lat, lon, np.array([5.0, 5.0001]), np.array([5.0, 5.0]), k)
        np.testing.assert_array_equal(idx, want_idx)
        np.testing.assert_array_equal(dist, want_dist)
    assert index.nearest(-30.0, 150.0, max_km=-1.0) == (-1, np.inf)
    with pytest.raises(ValueError):
        index.nearest(0.0, 0.0, k=0)
    with pytest.raises(ValueError):
        PointIndex([0.0, 1.0], [0.0])
    with pytest.raises(ValueError):
        PointIndex([95.0], [0.0])


# Remote queries: a world of points with an empty ocean in it, and queries far out in that ocean.
OCEAN = (-35.0, -125.0)
OCEAN_EMPTY_KM = 3000.0


@pytest.fixture(scope="module")
def ocean():
    rng = np.random.default_rng(21)
    lat, lon = _mixed_points(rng, 215_000)
    keep = haversine(OCEAN[0], OCEAN[1], lat, lon) > OCEAN_EMPTY_KM
    lat, lon = lat[keep][:200_000], lon[keep][:200_000]
    assert len(lat) == 200_000
    qlat, qlon = np.degrees(np.arcsin(rng.uniform(-1, 1, 800_000))), rng.uniform(-180, 180, 800_000)
    far = haversine(OCEAN[0], OCEAN[1], qlat, qlon) < OCEAN_EMPTY_KM - 500
    return PointIndex(lat, lon), lat, lon, qlat[far][:20_000], qlon[far][:20_000]


@pytest.mark.parametrize(
    ("where", "k", "max_km"), [("ocean", 1, None), ("ocean", 8, None), ("world", 8, 500.0)]
)
def test_remote_queries_stay_fast_and_small(ocean, where, k, max_km):
    """Regression: queries far from every point once grew their search blocks over whole
    continents, materialising every point in them (25 s and 13 GB for 20k mid-ocean queries)."""
    index, lat, lon, qlat, qlon = ocean
    if where == "world":
        rng = np.random.default_rng(22)
        qlat, qlon = np.degrees(np.arcsin(rng.uniform(-1, 1, 20_000))), rng.uniform(-180, 180, 20_000)
    index.nearest(qlat[:10], qlon[:10], k=k, max_km=max_km)  # build the index outside the guard
    tracemalloc.start()
    t = time.perf_counter()
    try:
        idx, dist = index.nearest(qlat, qlon, k=k, max_km=max_km)
        elapsed = time.perf_counter() - t
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert elapsed < 2.0, f"{elapsed:.2f} s"
    assert peak < 200e6, f"{peak / 1e6:.0f} MB"
    idx, dist = idx.reshape(len(qlat), k), dist.reshape(len(qlat), k)
    sub = np.random.default_rng(23).choice(len(qlat), 200, replace=False)
    want_idx, want_dist = _brute(lat, lon, qlat[sub], qlon[sub], k, max_km)
    np.testing.assert_array_equal(idx[sub], want_idx)
    np.testing.assert_allclose(dist[sub], want_dist, rtol=1e-12, atol=1e-9)
    if where == "ocean":
        assert (dist[:, 0] > 500).all()  # they really are remote


@pytest.mark.parametrize("budget", [None, 7])
def test_far_queries_small_batches_and_large_k(monkeypatch, budget):
    """Points in one corner of the world, queries everywhere (poles, antimeridian, antipodes):
    disks of every size on every grid level, read in batches of any size."""
    from placewise.packs import _points

    if budget:
        monkeypatch.setattr(_points, "_ROW_BUDGET", budget)
        monkeypatch.setattr(_points, "_PAIR_BUDGET", budget)
    rng = np.random.default_rng(31)
    lat = np.concatenate([rng.normal(48, 4, 400), rng.normal(-75, 3, 30), [89.99, -89.99]])
    lon = np.concatenate([rng.normal(15, 8, 400), rng.uniform(-180, 180, 30), [123.0, -45.0]])
    lat, lon = np.clip(lat, -90, 90), (lon + 180) % 360 - 180
    index = PointIndex(lat, lon, cell_deg=0.05)
    qlat, qlon = _mixed_points(rng, 300)
    qlat = np.concatenate([qlat, [90.0, -90.0, 0.0, -48.0, 10.0]])
    qlon = np.concatenate([qlon, [0.0, 180.0, -180.0, -165.0, 179.999]])
    for k, max_km in ((1, None), (4, None), (20, None), (3, 3000.0), (12, 9000.0)):
        idx, dist = index.nearest(qlat, qlon, k=k, max_km=max_km)
        want_idx, want_dist = _brute(lat, lon, qlat, qlon, k, max_km)
        idx, dist = idx.reshape(len(qlat), k), dist.reshape(len(qlat), k)
        np.testing.assert_array_equal(idx, want_idx)
        np.testing.assert_allclose(dist, want_dist, rtol=1e-12, atol=1e-9)
    for a, b in zip(qlat[:40], qlon[:40], strict=True):
        got_i, _ = index.within(a, b, 2500.0)
        d = haversine(a, b, lat, lon)
        want = np.flatnonzero(d <= 2500.0)
        np.testing.assert_array_equal(got_i, want[np.argsort(d[want], kind="stable")])
