"""Geometry shared by the pack writer and reader, so both see exactly the same numbers.

Polygons are planar in (lat, lon) degrees: the even-odd test below is the one placewise.geo.shapes
uses, with the same arithmetic in the same order, so a pack query and `Feature.contains` agree bit
for bit. Features that cross the antimeridian are stored split at ±180 (RFC 7946 §3.1.9).
"""

import itertools
import math

import numpy as np

from placewise.constants.packs import E7
from placewise.geo import normalize_lon

from ._lazy import Guarded

# pairs of (edge, point) examined at once by the even-odd test; bounds memory to ~0.5 GB worst case
_PAIR_BUDGET = 4_000_000
# Slabs builds every feature at once when asked for more than this many new ones
_BUILD_ALL_AFTER = 64
# Slabs.even_odd sorts the points instead when the features asked about have at most this many
# edges per point
_PAIRS_PER_POINT = 4
# margin, in degrees, by which edges are fattened when finding the cells they touch: far below the
# 1e-7 storage grid, far above float64 rounding at 180 degrees
_EPS = 1e-9


def to_e7(degrees):
    return np.round(np.asarray(degrees, dtype=np.float64) * E7).astype(np.int32)


def from_e7(values):
    return np.asarray(values, dtype=np.float64) / E7


def normalise(lat, lon):
    """Query points for the readers: longitudes outside ±180 wrapped (±180 itself kept: polygons
    are planar, so the two differ); latitudes outside ±90 or anything non-finite become NaN, which
    matches nothing."""
    lon = np.where((lon < -180) | (lon > 180), normalize_lon(lon), lon)
    bad = ~(np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90))
    if bad.any():
        lat, lon = np.where(bad, np.nan, lat), np.where(bad, np.nan, lon)
    return lat, lon


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
    inside[order] = _odd_crossings(slat, slon, lo, hi, ya, xa, yb, xb)
    return inside


def even_odd_pairs(lat, lon, feature, offsets, ya, xa, yb, xb):
    """`even_odd` for many (point, feature) pairs at once: whether each point lies inside its own
    feature, whose edges are ya[offsets[f]:offsets[f + 1]] (and likewise xa, yb, xb). Same rule,
    same arithmetic, same answers. Pairs are sorted by (feature, latitude rank) and each edge of the
    features asked about is paired with its own feature's points in its latitude span, so the work
    is the features' edges plus the crossings: best when there are many points per feature."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    feature = np.asarray(feature, dtype=np.int64)
    if len(lat) == 0:
        return np.zeros(0, dtype=bool)
    levels = np.unique(lat)
    width = len(levels) + 1
    key = feature * width + np.searchsorted(levels, lat)
    order = np.argsort(key, kind="stable")
    skey, slat, slon = key[order], lat[order], lon[order]
    feats = np.unique(feature)
    owner, edge = _expand(offsets[feats], offsets[feats + 1])
    base = feats[owner] * width
    e_ya, e_xa, e_yb, e_xb = ya[edge], xa[edge], yb[edge], xb[edge]
    # ymin <= lat  <=>  rank(lat) >= the first rank not below ymin; lat < ymax likewise
    lo = np.searchsorted(skey, base + np.searchsorted(levels, np.minimum(e_ya, e_yb), "left"), "left")
    hi = np.searchsorted(skey, base + np.searchsorted(levels, np.maximum(e_ya, e_yb), "left"), "left")
    inside = np.zeros(len(lat), dtype=bool)
    inside[order] = _odd_crossings(slat, slon, lo, hi, e_ya, e_xa, e_yb, e_xb)
    return inside


class Slabs(Guarded):
    """The edges of a layer's features listed under every latitude band (band_deg high) their
    latitude span touches, so the even-odd test of a point need only look at its own feature's
    edges in its own band: only they can cross its ray. Built per feature on first use (all at
    once when many are asked for); safe to share between threads."""

    def __init__(self, offsets, edges, band_deg):
        super().__init__()
        self.offsets = np.asarray(offsets, dtype=np.int64)  # feature f's edges: offsets[f]:offsets[f + 1]
        self.edges = tuple(np.asarray(e, dtype=np.float64) for e in edges)  # ya, xa, yb, xb
        self.band_deg = band_deg
        self.bands = math.ceil(round(180 / band_deg, 9))
        self.built = np.zeros(len(self.offsets) - 1, dtype=bool)
        self.key = np.zeros(0, dtype=np.int64)  # feature * bands + band, sorted
        self.edge = np.zeros(0, dtype=np.int64)

    def _band(self, lat):
        return np.clip(np.floor((lat + 90.0) / self.band_deg), 0, self.bands - 1).astype(np.int64)

    def add(self, features):
        with self._lock:
            self._add(features)

    def _add(self, features):
        new = np.unique(np.asarray(features, dtype=np.int64))
        new = new[~self.built[new]]
        if len(new) > _BUILD_ALL_AFTER:
            new = np.flatnonzero(~self.built)
        if not len(new):
            return
        owner, edge = _expand(self.offsets[new], self.offsets[new + 1])
        ya, yb = self.edges[0][edge], self.edges[2][edge]
        lo, hi = self._band(np.minimum(ya, yb)), self._band(np.maximum(ya, yb))
        which, band = _expand(lo, hi + 1)
        key = new[owner[which]] * self.bands + band  # sorted: features ascending, then bands
        edge = edge[which]
        order = np.argsort(key, kind="stable")
        key, edge = key[order], edge[order]
        # each feature's keys form their own range, so the new ones slot in between the old
        at = np.searchsorted(self.key, key)
        self.key, self.edge = np.insert(self.key, at, key), np.insert(self.edge, at, edge)
        self.built[new] = True

    def even_odd(self, lat, lon, feature):
        """`even_odd` of each point against its own feature's edges: same rule, same arithmetic,
        same answers."""
        lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        feature = np.asarray(feature, dtype=np.int64)
        n = len(lat)
        if n == 0:
            return np.zeros(0, dtype=bool)
        feats = np.unique(feature)
        if int(np.sum(self.offsets[feats + 1] - self.offsets[feats])) <= _PAIRS_PER_POINT * n:
            # many points per feature (grid corners, big batches): sorting them beats the bands
            return even_odd_pairs(lat, lon, feature, self.offsets, *self.edges)
        with self._lock:  # the slabs of these features, consistent with each other
            self._add(feats)
            slab_key, slab_edge = self.key, self.edge
        key = feature * self.bands + self._band(lat)
        start, stop = np.searchsorted(slab_key, key, "left"), np.searchsorted(slab_key, key, "right")
        parity = np.zeros(n, dtype=np.int64)
        cum = np.cumsum(stop - start)
        cuts = np.searchsorted(cum, np.arange(_PAIR_BUDGET, cum[-1], _PAIR_BUDGET), "left") if cum[-1] else []
        ya, xa, yb, xb = self.edges
        for c0, c1 in zip([0, *cuts], [*cuts, n], strict=True):
            point, k = _expand(start[c0:c1], stop[c0:c1])
            e = slab_edge[k]
            plat = lat[c0:c1][point]
            e_ya, e_xa, e_yb, e_xb = ya[e], xa[e], yb[e], xb[e]
            # the crossing rule of `even_odd` (ymin <= lat < ymax), then its arithmetic
            across = (e_ya > plat) != (e_yb > plat)
            point, plat, e_ya, e_xa, e_yb, e_xb = (
                point[across],
                plat[across],
                e_ya[across],
                e_xa[across],
                e_yb[across],
                e_xb[across],
            )
            x_cross = e_xa + (plat - e_ya) * (e_xb - e_xa) / (e_yb - e_ya)
            parity[c0:c1] += np.bincount(point[lon[c0:c1][point] < x_cross], minlength=c1 - c0)
        return (parity & 1).astype(bool)


def _odd_crossings(slat, slon, lo, hi, ya, xa, yb, xb):
    """For points sorted as given and edges each crossing the rays of points lo..hi-1: whether an
    odd number of crossings lie east of each point."""
    n = len(slat)
    total = int(np.sum(hi - lo))
    parity = np.zeros(n, dtype=np.int64)
    if total == 0:
        return parity.astype(bool)
    chunks = max(1, -(-total // _PAIR_BUDGET))
    bounds = np.linspace(0, n, chunks + 1).astype(np.int64)
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
    return (parity & 1).astype(bool)


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = np.maximum(stop - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)


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
