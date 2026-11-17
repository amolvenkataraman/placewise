"""The polygon grid index of docs/pack-format.md, built for every feature of a layer at once.

A feature is a candidate in a cell when it may contain some point of it: an edge touches the cell,
or it covers the cell wholly (a feature whose bbox touches a cell but whose shape misses it is left
out). A cell is marked `inside` f when f covers it wholly (corners inside and no edge touching it,
so a cell in a hole is not) and every earlier candidate misses it entirely, so f is the first-match
answer for every point in it.

Everything is vectorised across features: the cells each edge touches, the cells each bbox
touches, and one even-odd test of the free cells' centres against their own feature's edges. The
arithmetic is that of `_geometry.edge_cell_pairs`, `bbox_cells` and `even_odd_rows`, element by
element, so the index is the one a per-feature loop over those functions builds.
"""

import numpy as np

from . import _geometry as gm

# edges handed to edge_cell_pairs at once, and (edge, latitude) pairs crossed at once: bounds the
# working memory to a few hundred MB whatever the layer's size
_EDGE_CHUNK = 1_000_000
_PAIR_CHUNK = 4_000_000


def build(geom, cell_deg):
    """(cell offsets, items, inside) for a polygon layer's geometry arrays (the geom/*.npy dict)."""
    rows, cols = gm.grid_shape(cell_deg)
    ncell = rows * cols
    lat, lon = gm.from_e7(geom["lat.npy"]), gm.from_e7(geom["lon.npy"])
    ring_off, part_off, feat_off = geom["ring.npy"], geom["part.npy"], geom["feature.npy"]
    nxt = gm.ring_next(ring_off, len(lat))
    edges = (lat, lon, lat[nxt], lon[nxt])
    vertex_off = ring_off[part_off[feat_off]]  # feature f's vertices (and edges): [f], [f + 1]
    count = len(feat_off) - 1
    edge_feature = np.repeat(np.arange(count, dtype=np.int64), np.diff(vertex_off))

    on_edge = _edge_keys(edges, edge_feature, cell_deg, rows, cols, ncell)
    cand_feature, cand_cell = _bbox_cells(gm.from_e7(geom["bbox.npy"]), cell_deg, rows, cols)
    key = cand_feature * ncell + cand_cell
    at = np.searchsorted(on_edge, key)
    touched = at < len(on_edge)
    touched[touched] = on_edge[at[touched]] == key[touched]
    free = ~touched
    free_cell, free_feature = cand_cell[free], cand_feature[free]
    # no edge touches a free cell, so its centre speaks for all of it
    centre_lat = -90.0 + (free_cell // cols + 0.5) * cell_deg
    centre_lon = -180.0 + (free_cell % cols + 0.5) * cell_deg
    covered = even_odd_grouped(centre_lat, centre_lon, free_feature, vertex_off, edges)

    cell = np.concatenate([cand_cell[touched], free_cell[covered]])
    feat = np.concatenate([cand_feature[touched], free_feature[covered]])
    stat = np.concatenate([np.full(touched.sum(), 2, np.int8), np.ones(covered.sum(), np.int8)])
    order = np.lexsort((feat, cell))
    cell, feat, stat = cell[order], feat[order], stat[order]
    offsets = np.zeros(ncell + 1, dtype=np.int64)
    np.cumsum(np.bincount(cell, minlength=ncell), out=offsets[1:])
    inside = np.full(ncell, -1, dtype=np.int32)
    first_cells, first = np.unique(cell, return_index=True)
    inside[first_cells] = np.where(stat[first] == 1, feat[first], -1)
    return offsets, feat.astype(np.int32), inside


def _edge_keys(edges, edge_feature, cell_deg, rows, cols, ncell):
    """Sorted unique feature * ncell + cell over every cell each feature's edges touch."""
    ya, xa, yb, xb = edges
    keys = []
    for s in range(0, len(ya), _EDGE_CHUNK):
        e = slice(s, s + _EDGE_CHUNK)
        cell, edge = gm.edge_cell_pairs(ya[e], xa[e], yb[e], xb[e], cell_deg, rows, cols)
        keys.append(np.unique(edge_feature[e][edge] * ncell + cell))
    return np.unique(np.concatenate([np.zeros(0, dtype=np.int64), *keys]))


def _bbox_cells(bbox, cell_deg, rows, cols):
    """(feature, cell) for every cell each feature's bbox touches, as gm.bbox_cells lists them
    (both sides of the antimeridian for a crossing box)."""
    south, west, north, east = bbox.T
    r0, r1 = gm.cell_rows(south, cell_deg, rows), gm.cell_rows(north, cell_deg, rows)
    cw, ce = gm.cell_cols(west, cell_deg, cols), gm.cell_cols(east, cell_deg, cols)
    crossing = west > east
    # column runs: [cw, ce] for an ordinary box; [cw, cols) then [0, ce] for a crossing one
    run_feature = np.concatenate([np.arange(len(bbox)), np.flatnonzero(crossing)])
    run_start = np.concatenate([cw, np.zeros(crossing.sum(), dtype=np.int64)])
    run_stop = np.concatenate([np.where(crossing, cols - 1, ce), ce[crossing]]) + 1
    owner, col = _expand(run_start, run_stop)
    col_feature = run_feature[owner]
    order = np.argsort(col_feature, kind="stable")  # each feature's columns, in bbox_cells order
    col_feature, col = col_feature[order], col[order]
    # every row of the feature with each of its columns: rows outer, columns inner
    ncols = np.bincount(col_feature, minlength=len(bbox))
    first_col = np.cumsum(ncols) - ncols
    owner, row = _expand(r0, r1 + 1)
    which, k = _expand(np.zeros(len(owner), dtype=np.int64), ncols[owner])
    feature = owner[which]
    cell = row[which] * cols + col[first_col[feature] + k]
    return feature, cell


def even_odd_grouped(lat, lon, feature, offsets, edges):
    """Which points lie inside their own feature, whose edges are edges[offsets[f]:offsets[f + 1]]:
    `gm.even_odd_rows` with each (feature, latitude) as a row, so many features' points that share
    a few latitudes are tested in one pass. Same rule, same arithmetic, same answers."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    inside = np.zeros(len(lat), dtype=bool)
    if not len(lat):
        return inside
    ya, xa, yb, xb = edges
    levels = np.unique(lat)
    width = len(levels) + 1
    groups, point_group = np.unique(feature * width + np.searchsorted(levels, lat), return_inverse=True)
    point_group = point_group.ravel()
    group_lat = levels[groups % width]
    feats = np.unique(feature)
    owner, edge = _expand(offsets[feats], offsets[feats + 1])
    base = feats[owner] * width
    e_ya, e_yb = ya[edge], yb[edge]
    # rows the edge's ray test applies to: ymin <= lat < ymax, as in even_odd_rows
    lo = np.searchsorted(groups, base + np.searchsorted(levels, np.minimum(e_ya, e_yb), "left"), "left")
    hi = np.searchsorted(groups, base + np.searchsorted(levels, np.maximum(e_ya, e_yb), "left"), "left")
    spans = np.flatnonzero(hi > lo)
    edge, lo, hi = edge[spans], lo[spans], hi[spans]
    group_parts, x_parts = [], []
    cum = np.cumsum(hi - lo)
    cuts = np.searchsorted(cum, np.arange(_PAIR_CHUNK, cum[-1] if len(cum) else 0, _PAIR_CHUNK), "left")
    for c0, c1 in zip([0, *cuts], [*cuts, len(edge)], strict=True):
        which, group = _expand(lo[c0:c1], hi[c0:c1])
        e = edge[c0:c1][which]
        x_parts.append(xa[e] + (group_lat[group] - ya[e]) * (xb[e] - xa[e]) / (yb[e] - ya[e]))
        group_parts.append(group)
    edge_group = np.concatenate([np.zeros(0, dtype=np.int64), *group_parts])
    x_cross = np.concatenate([np.zeros(0), *x_parts])
    total = np.bincount(edge_group, minlength=len(groups))
    # merge crossings and points per group, by longitude; at a tie the crossing sorts first, since
    # a crossing exactly at the point's longitude is not east of it
    row = np.concatenate([edge_group, point_group])
    x = np.concatenate([x_cross, lon])
    is_edge = np.concatenate([np.ones(len(edge_group), dtype=bool), np.zeros(len(lat), dtype=bool)])
    order = np.lexsort((~is_edge, x, row))
    seen = np.cumsum(is_edge[order])
    row_first = np.searchsorted(row[order], np.arange(len(groups)), "left")
    before_row = np.concatenate([[0], seen])[row_first]
    position = np.empty(len(order), dtype=np.int64)
    position[order] = np.arange(len(order))
    p = position[len(edge_group) :]
    east = total[point_group] - (seen[p] - before_row[point_group])
    inside[:] = (east & 1).astype(bool)
    return inside


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    start = np.asarray(start, dtype=np.int64)
    counts = np.maximum(np.asarray(stop, dtype=np.int64) - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)
