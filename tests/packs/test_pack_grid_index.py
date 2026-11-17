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
