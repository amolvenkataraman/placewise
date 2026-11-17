"""Nearest-neighbour and radius search over a point layer, with exact haversine distances.

Points are sorted by grid cell (id = row * cols + col), so the points of any run of cells along a
row are one contiguous slice found by binary search; nothing is stored per cell. A query searches
square blocks of cells growing outward from its own cell and stops once it has k points and no
unvisited cell can hold a closer one.
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.packs import POINT_CELL_DEGS, POINT_CELL_TARGET
from placewise.geo import bbox_around, bbox_split, haversine

from . import _geometry as gm

# lower bounds are shaved by this much (km) so float rounding can't stop a search early
_SLACK_KM = 1e-9
# up to this k, the k best are picked by repeated minima rather than a full sort
_SELECT_K = 8
_NO_INDEX = np.iinfo(np.int64).max


def choose_cell_deg(lat, lon):
    """The coarsest grid where a point's cell holds at most POINT_CELL_TARGET points on average.
    Averaged over points rather than cells, so dense clusters (cities) get small cells; searches
    in sparse areas then take more steps, but blocks grow geometrically, so not many more."""
    for cell_deg in sorted(POINT_CELL_DEGS, reverse=True):
        rows, cols = gm.grid_shape(cell_deg)
        ids = gm.cell_rows(lat, cell_deg, rows) * cols + gm.cell_cols(lon, cell_deg, cols)
        counts = np.unique(ids, return_counts=True)[1].astype(np.float64)
        if np.sum(counts * counts) <= POINT_CELL_TARGET * len(lat):
            return cell_deg
    return min(POINT_CELL_DEGS)


class PointGrid:
    def __init__(self, lat, lon, cell_deg=None):
        self.lat, self.lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        self.cell_deg = cell_deg or (choose_cell_deg(self.lat, self.lon) if len(self.lat) else 90.0)
        self.rows, self.cols = gm.grid_shape(self.cell_deg)
        ids = self._rows(self.lat) * self.cols + self._cols(self.lon)
        self.order = np.argsort(ids, kind="stable")
        self.ids = ids[self.order]
        self.slat, self.slon = self.lat[self.order], self.lon[self.order]

    def _rows(self, lat):
        return gm.cell_rows(lat, self.cell_deg, self.rows)

    def _cols(self, lon):
        return gm.cell_cols(lon, self.cell_deg, self.cols)

    def nearest(self, lat, lon, k, max_km=None):
        """(indexes (q, k), distances (q, k)) for flat query arrays, nearest first, ties to the lower
        index; -1 and inf where fewer than k points exist (within max_km)."""
        q = len(lat)
        best_i = np.full((q, k), -1, dtype=np.int64)
        best_d = np.full((q, k), np.inf)
        active = np.flatnonzero(np.isfinite(lat) & np.isfinite(lon))
        if not len(self.ids) or not len(active):
            return best_i, best_d
        r0, c0 = self._rows(lat[active]), self._cols(lon[active])
        prev = -1
        radius = 0
        while len(active):
            qpos, point = self._annulus(r0, c0, prev, radius)
            d = haversine(lat[active][qpos], lon[active][qpos], self.slat[point], self.slon[point])
            # only candidates nearer than a query's current k-th can change its answer
            limit = best_d[active, k - 1][qpos]
            if max_km is not None:
                limit = np.minimum(limit, max_km)
            keep = d <= limit
            qpos, point, d = qpos[keep], point[keep], d[keep]
            self._merge(best_i, best_d, active, qpos, self.order[point], d, k)

            bound = self._bound(lat[active], lon[active], r0, c0, radius)
            kth = best_d[active, k - 1]
            everything = (r0 - radius <= 0) & (r0 + radius + 1 >= self.rows) & (2 * radius + 1 >= self.cols)
            done = (kth <= bound) | everything
            if max_km is not None:
                done |= bound > max_km
            active, r0, c0 = active[~done], r0[~done], c0[~done]
            prev, radius = radius, radius + max(1, radius // 2)  # grow ~1.5x: few steps in empty areas
        return best_i, best_d

    def within(self, lat, lon, radius_km):
        """(indexes, distances) of the points within radius_km of one point, nearest first."""
        if not len(self.ids) or not (math.isfinite(lat) and math.isfinite(lon)):
            return np.zeros(0, dtype=np.int64), np.zeros(0)
        slices = []
        for south, west, north, east in bbox_split(bbox_around(lat, lon, radius_km)):
            margin = 1e-9  # degrees; bbox_around's edges are computed, not exact
            rows = np.arange(self._rows(south - margin), self._rows(north + margin) + 1)
            c_lo, c_hi = self._cols(west - margin), self._cols(east + margin)
            slices.append(self._slices(rows, np.full(len(rows), c_lo), np.full(len(rows), c_hi)))
        start = np.concatenate([s for s, _ in slices])
        stop = np.concatenate([e for _, e in slices])
        point = _expand(start, stop)[1]
        point = np.unique(point)  # the two halves of a split box can share an edge column
        d = haversine(lat, lon, self.slat[point], self.slon[point])
        keep = d <= radius_km
        index, d = self.order[point[keep]], d[keep]
        order = np.lexsort((index, d))
        return index[order], d[order]

    @staticmethod
    def _merge(best_i, best_d, active, qpos, index, d, k):
        """Fold new (query, point, distance) candidates into each query's k best, nearest first,
        equal distances to the lower index."""
        if not len(qpos):
            return
        queries = np.unique(qpos)  # only these can change
        rows = active[queries]
        nq = len(queries)
        q = np.concatenate([np.repeat(np.arange(nq), k), np.searchsorted(queries, qpos)])
        i = np.concatenate([best_i[rows].ravel(), index])
        dd = np.concatenate([best_d[rows].ravel(), d])
        new_i, new_d = np.full((nq, k), -1, dtype=np.int64), np.full((nq, k), np.inf)
        if k > _SELECT_K:
            order = np.lexsort((i, dd, q))
            q, i, dd = q[order], i[order], dd[order]
            rank = np.arange(len(q)) - np.searchsorted(q, np.arange(nq))[q]
            top = (rank < k) & (i >= 0)
            new_i[q[top], rank[top]], new_d[q[top], rank[top]] = i[top], dd[top]
        else:
            # k rounds of "take each query's minimum" beat sorting everything when k is small
            order = np.argsort(q, kind="stable")  # mostly in order already, so cheap
            i, dd = i[order], dd[order]
            starts = np.flatnonzero(np.diff(q[order], prepend=-1))
            counts = np.diff(np.append(starts, len(q)))
            key = np.where(i >= 0, i, _NO_INDEX)
            for j in range(k):
                m = np.minimum.reduceat(dd, starts)
                is_min = dd == np.repeat(m, counts)
                mi = np.minimum.reduceat(np.where(is_min, key, _NO_INDEX), starts)
                ok = np.isfinite(m)
                new_d[ok, j], new_i[ok, j] = m[ok], mi[ok]
                if j + 1 < k:
                    dd = np.where(is_min & (key == np.repeat(mi, counts)), np.inf, dd)
        best_i[rows], best_d[rows] = new_i, new_d

    def _slices(self, rows, c_lo, c_hi):
        """[start, stop) into the sorted points for the cells c_lo..c_hi of each row."""
        start = np.searchsorted(self.ids, rows * self.cols + c_lo, "left")
        stop = np.searchsorted(self.ids, rows * self.cols + c_hi, "right")
        return start, stop

    def _annulus(self, r0, c0, prev, radius):
        """(query position, sorted point index) pairs for the cells in the block of `radius` around
        each query's cell but not in the block of `prev` (-1: none)."""
        dr, lo, length = _ring_spans(prev, radius, self.cols)
        nq, ns = len(r0), len(dr)
        query = np.repeat(np.arange(nq), ns)
        row = np.repeat(r0, ns) + np.tile(dr, nq)
        lo = (np.repeat(c0, ns) + np.tile(lo, nq)) % self.cols
        length = np.tile(length, nq)
        ok = (row >= 0) & (row < self.rows) & (length > 0)
        query, row, lo, length = query[ok], row[ok], lo[ok], length[ok]
        # a span running past the last column continues from column 0
        first = np.minimum(length, self.cols - lo)
        wrap = length - first
        query = np.concatenate([query, query[wrap > 0]])
        rows = np.concatenate([row, row[wrap > 0]])
        c_lo = np.concatenate([lo, np.zeros(int((wrap > 0).sum()), dtype=np.int64)])
        c_hi = np.concatenate([lo + first - 1, wrap[wrap > 0] - 1])
        start, stop = self._slices(rows, c_lo, c_hi)
        which, point = _expand(start, stop)
        return query[which], point

    def _bound(self, lat, lon, r0, c0, radius):
        """Lower bound (km) on the distance from each query to any point outside its block."""
        cd = self.cell_deg
        south = np.where(r0 - radius <= 0, np.inf, lat - (-90.0 + (r0 - radius) * cd))
        north = np.where(r0 + radius + 1 >= self.rows, np.inf, (-90.0 + (r0 + radius + 1) * cd) - lat)
        bound = np.radians(np.minimum(south, north)) * MEAN_RADIUS_KM  # haversine >= R * |dlat|
        if 2 * radius + 1 < self.cols:
            # leaving the block sideways means crossing one of its bounding meridians; the nearest
            # point of a half-meridian dlon away is asin(cos(lat) sin(dlon)), or a pole past 90°
            lon_w = -180.0 + (c0 - radius) * cd
            lon_e = -180.0 + (c0 + radius + 1) * cd
            dlon = np.minimum(lon - lon_w, lon_e - lon)
            dlon = np.radians(np.clip(dlon, 0.0, 90.0))
            side = np.arcsin(np.clip(np.cos(np.radians(lat)) * np.sin(dlon), 0.0, 1.0)) * MEAN_RADIUS_KM
            bound = np.minimum(bound, side)
        return bound - _SLACK_KM


def _ring_spans(prev, radius, cols):
    """For the cells in the block of `radius` but not of `prev`, relative to the centre cell: one
    (row offset, first column offset, column count) per contiguous run along a row."""
    dr, lo, length = [], [], []
    full = 2 * radius + 1 >= cols
    for d in range(-radius, radius + 1):
        if abs(d) > prev:  # a row the previous block didn't reach: all of it
            spans = [(0, cols)] if full else [(-radius, 2 * radius + 1)]
        elif 2 * prev + 1 >= cols:
            spans = []
        elif full:  # the rest of the circle round from the previous block's east edge
            spans = [(prev + 1, cols - (2 * prev + 1))]
        else:
            spans = [(-radius, radius - prev), (prev + 1, radius - prev)]
        for a, n in spans:
            dr.append(d)
            lo.append(a)
            length.append(n)
    return np.asarray(dr, dtype=np.int64), np.asarray(lo, dtype=np.int64), np.asarray(length, dtype=np.int64)


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = np.maximum(stop - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)
