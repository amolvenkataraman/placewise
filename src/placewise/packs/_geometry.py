"""Geometry shared by the pack writer and reader, so both see exactly the same numbers.

Polygons are planar in (lat, lon) degrees: the even-odd test below is the one placewise.geo.shapes
uses, with the same arithmetic in the same order, so a pack query and `Feature.contains` agree bit
for bit. Features that cross the antimeridian are stored split at ±180 (RFC 7946 §3.1.9).
"""

import itertools
import math

import numpy as np

from placewise.constants.packs import E7

# pairs of (edge, point) examined at once by the even-odd test; bounds memory to ~0.5 GB worst case
_PAIR_BUDGET = 4_000_000
# margin, in degrees, by which edges are fattened when finding the cells they touch: far below the
# 1e-7 storage grid, far above float64 rounding at 180 degrees
_EPS = 1e-9


def to_e7(degrees):
    return np.round(np.asarray(degrees, dtype=np.float64) * E7).astype(np.int32)


def from_e7(values):
    return np.asarray(values, dtype=np.float64) / E7


def grid_shape(cell_deg):
    # round first so 180 / 0.1 = 1800.0000000000002 doesn't become 1801 rows
    return math.ceil(round(180 / cell_deg, 9)), math.ceil(round(360 / cell_deg, 9))


def cell_rows(lat, cell_deg, rows):
    """Grid row of each latitude. Edges belong to the cell to the north; 90 falls in the last row."""
    return np.clip(np.floor((np.asarray(lat) + 90.0) / cell_deg), 0, rows - 1).astype(np.int64)


def cell_cols(lon, cell_deg, cols):
    """Grid column of each longitude. Edges belong to the cell to the east; 180 falls in the last
    column (not wrapped to -180: polygon geometry is planar, so 180 and -180 are different places)."""
    return np.clip(np.floor((np.asarray(lon) + 180.0) / cell_deg), 0, cols - 1).astype(np.int64)


def ring_next(ring_offsets, count):
    """For each vertex, the index of the next vertex round its ring (rings are stored open)."""
    nxt = np.arange(1, count + 1, dtype=np.int64)
    ring_offsets = np.asarray(ring_offsets, dtype=np.int64)
    starts, ends = ring_offsets[:-1], ring_offsets[1:]
    nonempty = ends > starts
    nxt[ends[nonempty] - 1] = starts[nonempty]
    return nxt


def even_odd(lat, lon, ya, xa, yb, xb):
    """Which points lie inside the rings whose edges run (ya, xa) -> (yb, xb): even-odd rule, a ray
    to the east, exactly as placewise.geo.shapes.contains. Points on an edge may land either way.

    Instead of testing every point against every edge, points are sorted by latitude and each edge
    is paired only with the points in its latitude span, so the work grows with the number of edges
    each point's ray actually meets."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    n = len(lat)
    inside = np.zeros(n, dtype=bool)
    if n == 0 or len(ya) == 0:
        return inside
    order = np.argsort(lat, kind="stable")
    slat, slon = lat[order], lon[order]
    ymin, ymax = np.minimum(ya, yb), np.maximum(ya, yb)
    # an edge crosses the ray from (lat, lon) when ymin <= lat < ymax, as (ya > lat) != (yb > lat)
    lo = np.searchsorted(slat, ymin, "left")
    hi = np.searchsorted(slat, ymax, "left")
    total = int(np.sum(hi - lo))
    if total == 0:
        return inside
    chunks = max(1, -(-total // _PAIR_BUDGET))
    bounds = np.linspace(0, n, chunks + 1).astype(np.int64)
    parity = np.zeros(n, dtype=np.int64)
    for c0, c1 in itertools.pairwise(bounds):
        clo, chi = np.clip(lo, c0, c1), np.clip(hi, c0, c1)
        counts = chi - clo
        crossing = np.flatnonzero(counts)
        if not len(crossing):
            continue
        counts = counts[crossing]
        edge = np.repeat(crossing, counts)
        first = np.cumsum(counts) - counts
        pos = np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - clo[crossing], counts)
        e_ya, e_xa, e_yb, e_xb = ya[edge], xa[edge], yb[edge], xb[edge]
        x_cross = e_xa + (slat[pos] - e_ya) * (e_xb - e_xa) / (e_yb - e_ya)
        parity += np.bincount(pos[slon[pos] < x_cross], minlength=n)
    inside[order] = (parity & 1).astype(bool)
    return inside


def even_odd_rows(lat, lon, ya, xa, yb, xb):
    """`even_odd` for points that share a few latitudes, such as grid cell centres or corners:
    each edge is paired with each distinct latitude it spans, not with each point, and points are
    then counted against their row's sorted crossings. Same rule, same arithmetic, same answers."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    inside = np.zeros(len(lat), dtype=bool)
    if len(lat) == 0 or len(ya) == 0:
        return inside
    rows, point_row = np.unique(lat, return_inverse=True)
    point_row = point_row.ravel()
    lo = np.searchsorted(rows, np.minimum(ya, yb), "left")
    hi = np.searchsorted(rows, np.maximum(ya, yb), "left")
    counts = hi - lo
    edge = np.repeat(np.arange(len(ya)), counts)
    edge_row = np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(
        np.cumsum(counts) - counts - lo, counts
    )
    x_cross = xa[edge] + (rows[edge_row] - ya[edge]) * (xb[edge] - xa[edge]) / (yb[edge] - ya[edge])
    # merge crossings and points per row, ordered by longitude; at a tie the crossing sorts first,
    # since a crossing exactly at the point's longitude is not east of it
    row = np.concatenate([edge_row, point_row])
    x = np.concatenate([x_cross, lon])
    is_edge = np.concatenate([np.ones(len(edge_row), dtype=bool), np.zeros(len(lat), dtype=bool)])
    order = np.lexsort((~is_edge, x, row))
    seen = np.cumsum(is_edge[order])  # crossings at or before each sorted position
    row_first = np.searchsorted(row[order], np.arange(len(rows)), "left")
    before_row = np.concatenate([[0], seen])[row_first]
    total = np.bincount(edge_row, minlength=len(rows))
    position = np.empty(len(order), dtype=np.int64)
    position[order] = np.arange(len(order))
    p = position[len(edge_row) :]
    east = total[point_row] - (seen[p] - before_row[point_row])
    inside[:] = (east & 1).astype(bool)
    return inside


def edge_cells(ya, xa, yb, xb, cell_deg, rows, cols):
    """Ids (row * cols + col, unique) of every grid cell whose closed rectangle an edge touches.

    Conservative: edges are fattened by a hair, so a cell may be reported that an edge only nearly
    touches, but never is one missed (a miss would wrongly mark a cell as wholly inside)."""
    return np.unique(edge_cell_pairs(ya, xa, yb, xb, cell_deg, rows, cols)[0])


def edge_cell_pairs(ya, xa, yb, xb, cell_deg, rows, cols):
    """(cell id, edge index) for every cell each edge touches, as `edge_cells` finds them."""
    if len(ya) == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
    x0, x1 = np.minimum(xa, xb), np.maximum(xa, xb)
    c0 = np.clip(np.floor((x0 + 180.0 - _EPS) / cell_deg), 0, cols - 1).astype(np.int64)
    c1 = np.clip(np.floor((x1 + 180.0 + _EPS) / cell_deg), 0, cols - 1).astype(np.int64)
    # one entry per (edge, column strip it passes through)
    k = c1 - c0 + 1
    edge = np.repeat(np.arange(len(ya)), k)
    col = np.repeat(c0, k) + (np.arange(int(k.sum())) - np.repeat(np.cumsum(k) - k, k))
    sx0 = np.maximum(-180.0 + col * cell_deg - _EPS, x0[edge])
    sx1 = np.minimum(-180.0 + (col + 1) * cell_deg + _EPS, x1[edge])
    sx1 = np.maximum(sx0, sx1)
    e_ya, e_xa, e_yb, e_xb = ya[edge], xa[edge], yb[edge], xb[edge]
    dx = e_xb - e_xa
    vertical = dx == 0
    safe_dx = np.where(vertical, 1.0, dx)
    t0 = np.clip((sx0 - e_xa) / safe_dx, 0.0, 1.0)
    t1 = np.clip((sx1 - e_xa) / safe_dx, 0.0, 1.0)
    y0, y1 = e_ya + t0 * (e_yb - e_ya), e_ya + t1 * (e_yb - e_ya)
    ylo = np.where(vertical, np.minimum(e_ya, e_yb), np.minimum(y0, y1))
    yhi = np.where(vertical, np.maximum(e_ya, e_yb), np.maximum(y0, y1))
    r0 = np.clip(np.floor((ylo + 90.0 - _EPS) / cell_deg), 0, rows - 1).astype(np.int64)
    r1 = np.clip(np.floor((yhi + 90.0 + _EPS) / cell_deg), 0, rows - 1).astype(np.int64)
    m = r1 - r0 + 1
    row = np.repeat(r0, m) + (np.arange(int(m.sum())) - np.repeat(np.cumsum(m) - m, m))
    return row * cols + np.repeat(col, m), np.repeat(edge, m)


def bbox_cells(south, west, north, east, cell_deg, rows, cols):
    """Ids of the cells a bbox touches, both sides when it crosses the antimeridian (west > east)."""
    r = np.arange(cell_rows(south, cell_deg, rows), cell_rows(north, cell_deg, rows) + 1)
    cw, ce = int(cell_cols(west, cell_deg, cols)), int(cell_cols(east, cell_deg, cols))
    c = np.arange(cw, ce + 1) if west <= east else np.concatenate([np.arange(cw, cols), np.arange(0, ce + 1)])
    return (r[:, None] * cols + c[None, :]).ravel()


def circular_lon_range(intervals):
    """(west, east) of the shortest longitude range covering every [lo, hi] interval (no interval
    itself crosses the antimeridian); west > east when the answer does. Integer e7 degrees."""
    spans = sorted((int(lo), int(hi)) for lo, hi in intervals)
    merged = [list(spans[0])]
    for lo, hi in spans[1:]:
        if lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    # leave out the widest gap; the gap round the back (east of the last, west of the first) means
    # no crossing, and wins ties so ordinary shapes never get a crossing box
    best_gap, west, east = merged[0][0] + 360 * E7 - merged[-1][1], merged[0][0], merged[-1][1]
    for a, b in itertools.pairwise(merged):
        if b[0] - a[1] > best_gap:
            best_gap, west, east = b[0] - a[1], b[0], a[1]
    return west, east
