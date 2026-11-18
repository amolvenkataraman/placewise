"""The vectorised grid index builds exactly what a per-feature loop over _geometry's functions
builds (the writer's grid before it was vectorised), on random shapes."""

import numpy as np
import pytest
from pack_kit import blob_features, box_feature, fiji

from placewise.model import Feature, Outline
from placewise.packs import _geometry as gm
from placewise.packs import _grid_index
from placewise.packs.writer import LayerData, _prepare


def _reference(geom, cell_deg):
    """The per-feature grid build, as packs/writer.py had it."""
    rows, cols = gm.grid_shape(cell_deg)
    lat, lon = gm.from_e7(geom["lat.npy"]), gm.from_e7(geom["lon.npy"])
    ring_off, part_off, feat_off = geom["ring.npy"], geom["part.npy"], geom["feature.npy"]
    nxt = gm.ring_next(ring_off, len(lat))
    bbox = gm.from_e7(geom["bbox.npy"])
    cells, feats, status = [], [], []
    for f in range(len(feat_off) - 1):
        vs, ve = ring_off[part_off[feat_off[f]]], ring_off[part_off[feat_off[f + 1]]]
        ya, xa, yb, xb = lat[vs:ve], lon[vs:ve], lat[nxt[vs:ve]], lon[nxt[vs:ve]]
        candidates = gm.bbox_cells(*bbox[f], cell_deg, rows, cols)
        on_edge = np.isin(candidates, gm.edge_cells(ya, xa, yb, xb, cell_deg, rows, cols))
        free = candidates[~on_edge]
        centre_lat = -90.0 + (free // cols + 0.5) * cell_deg
        centre_lon = -180.0 + (free % cols + 0.5) * cell_deg
        covered = free[gm.even_odd_rows(centre_lat, centre_lon, ya, xa, yb, xb)]
        cells += [candidates[on_edge], covered]
        feats.append(np.full(on_edge.sum() + len(covered), f, dtype=np.int64))
        status += [np.full(on_edge.sum(), 2, dtype=np.int8), np.ones(len(covered), dtype=np.int8)]
    cell = np.concatenate([np.zeros(0, dtype=np.int64), *cells])
    feat = np.concatenate([np.zeros(0, dtype=np.int64), *feats])
    stat = np.concatenate([np.zeros(0, dtype=np.int8), *status])
    order = np.lexsort((feat, cell))
    cell, feat, stat = cell[order], feat[order], stat[order]
    offsets = np.zeros(rows * cols + 1, dtype=np.int64)
    np.cumsum(np.bincount(cell, minlength=rows * cols), out=offsets[1:])
    inside = np.full(rows * cols, -1, dtype=np.int32)
    first_cells, first = np.unique(cell, return_index=True)
    inside[first_cells] = np.where(stat[first] == 1, feat[first], -1)
    return offsets, feat.astype(np.int32), inside


def _geom(features):
    n = len(features)
    layer = LayerData(
        "areas", "polygon", {"id": [f"a{i}" for i in range(n)], "name": ["a"] * n}, ("synthetic",),
        features=features,
    )  # fmt: skip
    return _prepare(layer).geom


def _wide_ring(south, west, north, east):
    """A box wider than 180 degrees, with a vertex half way along its long edges."""
    mid = (west + east) / 2
    return ((south, west), (south, mid), (south, east), (north, east), (north, mid), (north, west))


def _assert_same(features, cell_deg):
    geom = _geom(features)
    for got, want in zip(_grid_index.build(geom, cell_deg), _reference(geom, cell_deg), strict=True):
        assert got.dtype == want.dtype
        np.testing.assert_array_equal(got, want)


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("cell_deg", [1.0, 0.25, 5.0])
def test_random_shapes_with_holes_and_islands(seed, cell_deg):
    rng = np.random.default_rng(seed)
    features = blob_features(60, rng, radius=(0.2, 8.0), vertices=(5, 300), holes=True)
    _assert_same(features, cell_deg)


def test_boxes_on_cell_edges_nested_and_overlapping():
    features = [
        box_feature(0, 0, 10, 10, (3, 3, 7, 7)),
        box_feature(2, 2, 3.5, 3.5),
        box_feature(-1, -1, 1, 1),
        box_feature(0, 0, 10, 10),  # the same square again, later
        Feature(outlines=(Outline((_wide_ring(-89.5, -170.5, -60.25, 170.25),)),)),  # most longitudes
        box_feature(44.0000001, -80, 44.9999999, -79),
    ]
    _assert_same(features, 1.0)


def test_antimeridian_crossing_features():
    # Fiji's two halves, and a box that crosses the antimeridian with its columns wrapping
    wide = Feature(
        outlines=(
            Outline((((10.0, 170.5), (10.0, 180.0), (12.0, 180.0), (12.0, 170.5)),)),
            Outline((((10.0, -180.0), (10.0, -170.5), (12.0, -170.5), (12.0, -180.0)),)),
        )
    )
    # bbox west > east and both in one column: bbox_cells lists that column twice
    almost_round = Feature(
        outlines=(
            Outline((((20.0, 10.7), (20.0, 180.0), (21.5, 180.0), (21.5, 10.7)),)),
            Outline((_wide_ring(20.0, -180.0, 21.5, 10.2),)),
        )
    )
    _assert_same([fiji(), wide, almost_round, box_feature(-19, 175, -17, 178)], 1.0)


def test_no_features():
    offsets, items, inside = _grid_index.build(
        {
            "lat.npy": np.zeros(0, np.int32), "lon.npy": np.zeros(0, np.int32),
            "ring.npy": np.zeros(1, np.int64), "part.npy": np.zeros(1, np.int64),
            "feature.npy": np.zeros(1, np.int64), "bbox.npy": np.zeros((0, 4), np.int32),
        },
        1.0,
    )  # fmt: skip
    assert offsets.sum() == 0 and len(items) == 0 and (inside == -1).all()


def test_grouped_even_odd_matches_per_feature_even_odd():
    rng = np.random.default_rng(7)
    geom = _geom(blob_features(30, rng, radius=(0.5, 5.0), vertices=(5, 100), holes=True))
    lat, lon = gm.from_e7(geom["lat.npy"]), gm.from_e7(geom["lon.npy"])
    nxt = gm.ring_next(geom["ring.npy"], len(lat))
    edges = (lat, lon, lat[nxt], lon[nxt])
    offsets = geom["ring.npy"][geom["part.npy"][geom["feature.npy"]]]
    n = 20_000
    feature = rng.integers(0, 30, n)
    plat = np.round(rng.uniform(-75, 75, n), 0) + 0.5  # few distinct latitudes, as grid centres
    plon = rng.uniform(-180, 180, n)
    got = _grid_index.even_odd_grouped(plat, plon, feature, offsets, edges)
    want = np.zeros(n, dtype=bool)
    for f in range(30):
        s, e = offsets[f], offsets[f + 1]
        mine = feature == f
        want[mine] = gm.even_odd(plat[mine], plon[mine], *(a[s:e] for a in edges))
    np.testing.assert_array_equal(got, want)


# --- the grid cut to the layer's extent --------------------------------------------------------


def _uncrop(offsets, items, inside, meta, rows, cols):
    """The world grid back from a cropped one."""
    count, full_inside = np.zeros(rows * cols, dtype=np.int64), np.full(rows * cols, -1, dtype=np.int32)
    lists = {}
    for k in range(meta["rows"] * meta["cols"]):
        r, c = divmod(k, meta["cols"])
        cell = (r + meta["row0"]) * cols + (c + meta["col0"]) % cols
        lists[cell] = items[offsets[k] : offsets[k + 1]]
        count[cell], full_inside[cell] = len(lists[cell]), inside[k]
    full_offsets = np.zeros(rows * cols + 1, dtype=np.int64)
    np.cumsum(count, out=full_offsets[1:])
    full_items = np.concatenate([np.zeros(0, items.dtype), *(lists[c] for c in sorted(lists))])
    return full_offsets, full_items, full_inside


def _assert_crop_keeps_everything(features, cell_deg):
    rows, cols = gm.grid_shape(cell_deg)
    full = _grid_index.build(_geom(features), cell_deg)
    *cut, meta = _grid_index.crop(*full, rows, cols)
    assert len(cut[0]) == meta["rows"] * meta["cols"] + 1 and len(cut[2]) == meta["rows"] * meta["cols"]
    for got, want in zip(_uncrop(*cut, meta, rows, cols), full, strict=True):
        assert got.dtype == want.dtype
        np.testing.assert_array_equal(got, want)
    return meta


@pytest.mark.parametrize("cell_deg", [1.0, 0.25])
def test_crop_keeps_every_candidate_of_random_shapes(cell_deg):
    rng = np.random.default_rng(11)
    features = blob_features(40, rng, radius=(0.2, 3.0), vertices=(5, 200), lat_range=(30, 50), holes=True)
    meta = _assert_crop_keeps_everything(features, cell_deg)
    assert meta["rows"] * meta["cols"] < gm.grid_shape(cell_deg)[0] * gm.grid_shape(cell_deg)[1] / 4


def test_crop_wraps_round_the_antimeridian():
    meta = _assert_crop_keeps_everything([fiji(), box_feature(-19, 175, -17, 178)], 1.0)
    assert meta == {"rows": 4, "cols": 21, "row0": 71, "col0": 350}


def test_crop_of_a_world_layer_is_the_world_grid():
    wide = Feature(outlines=(Outline((_wide_ring(-89.5, -179.5, 89.5, 179.5),)),))
    meta = _assert_crop_keeps_everything([wide], 1.0)
    assert meta == {"rows": 180, "cols": 360, "row0": 0, "col0": 0}


def test_crop_of_no_features_is_empty():
    geom = _geom([box_feature(0, 0, 1, 1)])
    empty = {k: (v[:0] if k in ("lat.npy", "lon.npy", "bbox.npy") else v[:1] * 0) for k, v in geom.items()}
    offsets, items, inside, meta = _grid_index.crop(*_grid_index.build(empty, 1.0), 180, 360)
    assert meta == {"rows": 0, "cols": 0, "row0": 0, "col0": 0}
    assert offsets.tolist() == [0] and len(items) == 0 and len(inside) == 0


def test_cells_of_a_cropped_grid_and_of_a_world_grid():
    meta = {"cell_deg": 1.0, "rows": 4, "cols": 21, "row0": 71, "col0": 350}
    # rows -19..-15 (world rows 71..74), columns 170..180 and -180..-169 (350..359, 0..10)
    lat = np.array([-18.5, -18.5, -18.5, -15.5, -19.5, 90.0, -16.0, -17.0])
    lon = np.array([175.5, -175.5, 0.5, 175.5, 179.0, 175.0, -170.0, -169.0])
    got = _grid_index.cells(lat, lon, meta).tolist()
    assert got == [5, 14, -1, 3 * 21 + 5, -1, -1, 3 * 21 + 20, -1]
    world = {"cell_deg": 1.0, "rows": 180, "cols": 360}  # a grid written before grids were cut
    assert _grid_index.cells(np.array([90.0, -90.0]), np.array([180.0, -180.0]), world).tolist() == [
        179 * 360 + 359, 0,
    ]  # fmt: skip
