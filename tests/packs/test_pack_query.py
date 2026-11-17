import numpy as np
import pytest
from pack_kit import CREATED, blob_features, box_feature, brute_force, fiji, polygon_layer

from placewise.geo import nearest_point_on_polyline
from placewise.model import Feature
from placewise.packs import open_pack, write_pack

N_RANDOM = 50_000


def _open(tmp_path, features, cell_deg=1.0, name="areas"):
    path = write_pack(
        tmp_path, "test", "2026.11", [polygon_layer(features, name=name, cell_deg=cell_deg)], created=CREATED
    )
    return open_pack(path)[name]


SQUARE = box_feature(0, 0, 10, 10, (4, 4, 6, 6))
ISLANDS = Feature(outlines=(*box_feature(0, 20, 2, 22).outlines, *box_feature(0, 30, 2, 32).outlines))
OVERLAP = box_feature(8, 8, 12, 12)


def test_bboxes_is_every_bbox_at_once(tmp_path):
    layer = _open(tmp_path, [SQUARE, ISLANDS, OVERLAP])
    boxes = layer.bboxes()
    assert boxes.shape == (3, 4) and not boxes.flags.writeable
    for i in range(3):
        b = layer.bbox(i)
        assert boxes[i].tolist() == [b.south, b.west, b.north, b.east]


def test_scalar_queries_holes_overlaps_and_query_all(tmp_path):
    layer = _open(tmp_path, [SQUARE, ISLANDS, OVERLAP])
    assert layer.query(2, 2) == 0 and type(layer.query(2, 2)) is int
    assert layer.query(5, 5) == -1  # in the hole
    assert layer.query(1, 31) == 1
    assert layer.query(9, 9) == 0  # the earlier feature wins
    assert layer.query(11, 11) == 2
    assert layer.query_all(9, 9) == [0, 2]
    assert layer.query_all(5, 5) == []
    assert layer.query_all(50, 50) == []


def test_query_keeps_the_input_shape(tmp_path):
    layer = _open(tmp_path, [SQUARE, ISLANDS, OVERLAP])
    lats = np.array([[2.0, 5.0], [1.0, 50.0]])
    lons = np.array([[2.0, 5.0], [31.0, 50.0]])
    np.testing.assert_array_equal(layer.query(lats, lons), [[0, -1], [1, -1]])
    assert layer.query(np.array([]), np.array([])).shape == (0,)


def test_odd_inputs_do_not_crash(tmp_path):
    layer = _open(tmp_path, [box_feature(80, 170, 90, 180)])
    assert layer.query(90, 180) in (0, -1)  # on the edge: either answer is allowed
    assert layer.query(85, 175) == 0
    assert layer.query(85, 175 - 360) == 0  # longitudes outside ±180 are wrapped
    assert layer.query(np.nan, 0) == -1
    assert layer.query(95, 0) == -1


def _layers():
    rng = np.random.default_rng(42)
    return {
        "sparse": blob_features(40, rng),
        "dense_overlapping": blob_features(150, rng, radius=(0.5, 8.0), lat_range=(-20, 20)),
        "holes_and_islands": blob_features(60, rng, radius=(2.0, 7.0), holes=True),
        "antimeridian": [FIJI, *blob_features(20, rng, lat_range=(-60, 60))],
    }


FIJI = fiji()
LAYERS = _layers()


def _random_points(features, rng, n):
    """Half uniform over the world, half inside the features' boxes, where the work is; a tenth
    snapped to the 0.25 degree lattice (grid cell edges), plus the world's own edges."""
    boxes = np.array([_bbox(f) for f in features])
    pick = rng.integers(0, len(boxes), n // 2)
    s, w, nn, e = boxes[pick].T
    e = np.where(w > e, e + 360, e)
    lats = np.concatenate([rng.uniform(-90, 90, n - n // 2), rng.uniform(s, nn)])
    lons = np.concatenate([rng.uniform(-180, 180, n - n // 2), (rng.uniform(w, e) + 180) % 360 - 180])
    snap = rng.uniform(size=n) < 0.1
    lats[snap], lons[snap] = np.round(lats[snap] * 4) / 4, np.round(lons[snap] * 4) / 4
    edges = np.array(
        [[90, 0], [-90, 0], [0, 180], [0, -180], [90, 180], [-90, -180], [-17, 180], [-17, -180]]
    )
    return np.concatenate([lats, edges[:, 0]]), np.concatenate([lons, edges[:, 1]])


def _bbox(feature):
    """The feature's box, the short way round when it is split at the antimeridian."""
    if feature is FIJI:
        return (-19, 170, -16, -170)
    return feature.bbox.as_tuple()


@pytest.mark.parametrize("cell_deg", [0.25, 1.0, 5.0])
@pytest.mark.parametrize("kind", list(LAYERS))
def test_query_equals_brute_force(tmp_path, kind, cell_deg):
    features = LAYERS[kind]
    layer = _open(tmp_path, features, cell_deg=cell_deg)
    lats, lons = _random_points(features, np.random.default_rng(1), N_RANDOM)
    expected = brute_force(features, lats, lons)
    assert (expected >= 0).mean() > 0.2  # the comparison means something
    np.testing.assert_array_equal(layer.query(lats, lons), expected)


@pytest.mark.parametrize("kind", list(LAYERS))
def test_query_all_equals_brute_force(tmp_path, kind):
    features = LAYERS[kind]
    layer = _open(tmp_path, features)
    lats, lons = _random_points(features, np.random.default_rng(2), 300)
    hits = np.array([np.asarray(f.contains(lats, lons)) for f in features])
    for k in range(len(lats)):
        assert layer.query_all(lats[k], lons[k]) == np.flatnonzero(hits[:, k]).tolist()


@pytest.mark.parametrize("kind", list(LAYERS))
def test_query_every_equals_brute_force(tmp_path, kind):
    """The vectorised query_all: every (point, feature) pair, sorted by point then feature."""
    features = LAYERS[kind]
    layer = _open(tmp_path, features)
    lats, lons = _random_points(features, np.random.default_rng(4), 500)
    hits = np.array([np.asarray(f.contains(lats, lons)) for f in features])
    point, feature = layer.query_every(lats, lons)
    want_feature, want_point = np.nonzero(hits)
    order = np.lexsort((want_feature, want_point))
    np.testing.assert_array_equal(point, want_point[order])
    np.testing.assert_array_equal(feature, want_feature[order])


def test_query_every_overlaps_and_empty_input(tmp_path):
    layer = _open(tmp_path, [SQUARE, ISLANDS, OVERLAP])
    point, feature = layer.query_every([9, 5, 11, 50], [9, 5, 11, 50])
    assert point.tolist() == [0, 0, 2] and feature.tolist() == [0, 2, 2]
    assert [a.tolist() for a in layer.query_every([], [])] == [[], []]


@pytest.mark.parametrize("kind", list(LAYERS))
def test_inside_cells_never_change_an_answer(tmp_path, kind):
    features = LAYERS[kind]
    layer = _open(tmp_path, features, cell_deg=0.5)
    inside = np.asarray(layer.grid_inside)
    assert (inside >= 0).sum() > 10  # the optimisation is actually exercised
    lats, lons = _random_points(features, np.random.default_rng(3), N_RANDOM)
    with_inside = layer.query(lats, lons)
    layer.grid_inside = np.full_like(inside, -1)
    without = layer.query(lats, lons)
    np.testing.assert_array_equal(with_inside, without)

    # and every point of a marked cell really is in that feature first
    _, cols = layer.grid_shape
    rng = np.random.default_rng(4)
    marked = np.flatnonzero(inside >= 0)
    cells = rng.choice(marked, min(len(marked), 400), replace=False)
    lat = -90 + (cells // cols + rng.uniform(0, 1, len(cells))) * layer.cell_deg
    lon = -180 + (cells % cols + rng.uniform(0, 1, len(cells))) * layer.cell_deg
    np.testing.assert_array_equal(brute_force(features, lat, lon), inside[cells])


@pytest.mark.parametrize("refine_after", [0, 10**9])
def test_small_batches_and_both_containment_paths(tmp_path, monkeypatch, refine_after):
    from placewise.constants import packs as consts
    from placewise.packs import _geometry, _refine

    features = LAYERS["holes_and_islands"]
    layer = _open(tmp_path, features)
    lats, lons = _random_points(features, np.random.default_rng(6), 5000)
    monkeypatch.setattr(_geometry, "_PAIR_BUDGET", 50)  # many small chunks
    monkeypatch.setattr(_refine, "_PAIR_BUDGET", 50)
    monkeypatch.setattr(consts, "REFINE_AFTER_POINTS", refine_after)  # always / never refine
    np.testing.assert_array_equal(layer.query(lats, lons), brute_force(features, lats, lons))
    assert bool(layer._refined) == (refine_after == 0)


def _brute_edge_km(feature, lat, lon):
    best = np.inf
    for outline in feature.outlines:
        for ring in outline.rings:
            pts = np.array([*ring, ring[0]])
            keep = ~((np.abs(pts[:-1, 1]) == 180) & (np.abs(pts[1:, 1]) == 180))
            for a in np.flatnonzero(keep):
                best = min(best, nearest_point_on_polyline(lat, lon, pts[a : a + 2])[2])
    return best


def test_nearest_edge_km(tmp_path):
    layer = _open(tmp_path, [SQUARE, fiji(), *LAYERS["holes_and_islands"][:3]])
    # from the middle of the 0..4 strip of the square to its edges: 2 degrees of latitude
    assert layer.nearest_edge_km(2.0, 5.0, 0) == pytest.approx(2 * 111.195, rel=1e-3)
    # in the hole: the hole's own edge, about 1 degree away (edges are great circles, so not exactly)
    assert layer.nearest_edge_km(5.0, 5.0, 0) == pytest.approx(111.195, rel=1e-2)
    # the antimeridian cut is not a border: 179.9 E is 1.5 degrees from Fiji's real edges, not 0.1
    assert layer.nearest_edge_km(-17.5, 179.9, 1) == pytest.approx(1.5 * 111.195, rel=1e-2)
    rng = np.random.default_rng(5)
    for i in range(2, 5):
        feature = layer.feature(i)
        lats, lons = rng.uniform(-60, 60, 4), rng.uniform(-170, 170, 4)
        got = layer.nearest_edge_km(lats, lons, i)
        want = [_brute_edge_km(feature, a, b) for a, b in zip(lats, lons, strict=True)]
        np.testing.assert_allclose(got, want, rtol=1e-9)


def test_even_odd_rows_matches_even_odd():
    from placewise.packs import _geometry as gm

    rng = np.random.default_rng(8)
    ring = np.array(LAYERS["sparse"][0].outlines[0].rings[0])
    ya, xa = ring[:, 0], ring[:, 1]
    yb, xb = np.roll(ya, -1), np.roll(xa, -1)
    # shared latitudes, some equal to vertex latitudes, longitudes some equal to crossings
    lats = rng.choice(np.concatenate([ya[:20], rng.uniform(ya.min() - 1, ya.max() + 1, 30)]), 4000)
    lons = np.concatenate([rng.uniform(xa.min() - 1, xa.max() + 1, 3990), xa[:10]])
    np.testing.assert_array_equal(
        gm.even_odd_rows(lats, lons, ya, xa, yb, xb), gm.even_odd(lats, lons, ya, xa, yb, xb)
    )


def test_shapes_on_the_grid_lines(tmp_path):
    """Boxes whose edges run along cell and fine-cell lines (like borders on parallels and
    meridians), queried on that same lattice: the degenerate cases for every shortcut."""
    features = [box_feature(s, w, s + 2, w + 3) for s in range(30, 40, 2) for w in range(-110, -90, 3)]
    features += [box_feature(29, -111, 41, -88, (33.125, -100.25, 35.5, -97))]  # a frame behind them
    layer = _open(tmp_path, features)
    rng = np.random.default_rng(9)
    lats = np.concatenate([rng.uniform(28, 42, 20_000), np.round(rng.uniform(28, 42, 20_000) * 8) / 8])
    lons = np.concatenate([rng.uniform(-112, -87, 20_000), np.round(rng.uniform(-112, -87, 20_000) * 8) / 8])
    np.testing.assert_array_equal(layer.query(lats, lons), brute_force(features, lats, lons))


@pytest.mark.parametrize("refine_after", [0, 10**9])
def test_query_work_is_vectorised_across_features(tmp_path, monkeypatch, refine_after):
    """Each round of candidates is tested in a few array calls for all its features together, not
    in a Python loop per feature: the call count stays flat however many features are hit."""
    from placewise.constants import packs as consts
    from placewise.packs import _geometry

    features = LAYERS["dense_overlapping"]
    layer = _open(tmp_path, features)
    monkeypatch.setattr(consts, "REFINE_AFTER_POINTS", refine_after)
    calls = []
    for name in [n for n in dir(_geometry) if n.startswith("even_odd")]:
        real = getattr(_geometry, name)
        monkeypatch.setattr(
            _geometry, name, lambda *a, _real=real, _name=name: calls.append(_name) or _real(*a)
        )
    if hasattr(_geometry, "Slabs"):
        slabs = _geometry.Slabs.even_odd
        monkeypatch.setattr(
            _geometry.Slabs, "even_odd", lambda *a: calls.append("Slabs.even_odd") or slabs(*a)
        )
    lats, lons = _random_points(features, np.random.default_rng(10), 20_000)
    got = layer.query(lats, lons)
    np.testing.assert_array_equal(got, brute_force(features, lats, lons))
    hit = len(np.unique(got[got >= 0]))
    assert hit > 100  # most features get points
    assert len(calls) < 40, f"{len(calls)} even-odd calls for {hit} features"
