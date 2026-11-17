"""In-memory indexes the lookup builds over pack layers, lazily, the first time it needs them.

- EdgeIndex: every boundary edge of a polygon layer binned into grid cells, answering "which
  features have a boundary within r km of each point, and how far" exactly (r is small).
- SampleIndex: boundaries sampled every few km, answering "nearest feature" over long distances.
- PointIndex: nearest-neighbour over a subset of a point layer.

Polygon geometry is read from the pack's documented files (docs/pack-format.md, "Polygon layers").
"""

import itertools
import math

import numpy as np

from placewise.constants import lookup as const
from placewise.constants.earth import MEAN_RADIUS_KM

# The packs reader's grid search is exactly what a subset of points needs; it isn't public yet
# (requested: a public PointIndex in placewise.packs), so it is imported from one place only.
from placewise.packs._points import PointGrid

KM_PER_DEG = math.pi * MEAN_RADIUS_KM / 180
_E7 = 1e-7
_PAIR_BLOCK = 2_000_000  # (point, edge) pairs evaluated at once, to bound memory


def _polygon_edges(layer):
    """(a_lat, a_lon, b_lat, b_lon, feature) for every boundary edge of a polygon layer, leaving out
    edges along ±180 where antimeridian features are cut (they are not borders)."""
    geom = layer.path / "geom"

    def load(name):
        return np.load(geom / f"{name}.npy", mmap_mode="r", allow_pickle=False)

    lat = np.asarray(load("lat"), dtype=np.float64) * _E7
    lon = np.asarray(load("lon"), dtype=np.float64) * _E7
    ring, part, feature = (np.asarray(load(n), dtype=np.int64) for n in ("ring", "part", "feature"))
    ring_part = np.repeat(np.arange(len(part) - 1), np.diff(part))
    part_feature = np.repeat(np.arange(len(feature) - 1), np.diff(feature))
    owner = np.repeat(part_feature[ring_part], np.diff(ring))
    nxt = np.arange(1, len(lat) + 1)
    nonempty = ring[1:] > ring[:-1]
    nxt[ring[1:][nonempty] - 1] = ring[:-1][nonempty]  # each ring closes on its first vertex
    b_lat, b_lon = lat[nxt], lon[nxt]
    keep = ~((np.abs(lon) == 180) & (np.abs(b_lon) == 180))
    return lat[keep], lon[keep], b_lat[keep], b_lon[keep], owner[keep]


def _samples(a_lat, a_lon, b_lat, b_lon, step_deg):
    """Points along each edge no more than step_deg apart (endpoints included): (edge, lat, lon)."""
    extent = np.maximum(np.abs(b_lat - a_lat), np.abs(b_lon - a_lon))
    n = np.ceil(extent / step_deg).astype(np.int64) + 1
    edge = np.repeat(np.arange(len(n)), n)
    k = np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)
    t = k / np.maximum(n[edge] - 1, 1)
    return edge, a_lat[edge] + t * (b_lat - a_lat)[edge], a_lon[edge] + t * (b_lon - a_lon)[edge]


def best_per_query(q, value, n):
    """For pairs (q, value), the position of the smallest value per q: an (n,) array, -1 where q
    has no pair. Ties go to the earlier pair."""
    best = np.full(n, -1, dtype=np.int64)
    if len(q):
        order = np.lexsort((np.arange(len(q)), value, q))
        first = np.flatnonzero(np.diff(q[order], prepend=-1))
        best[q[order][first]] = order[first]
    return best


class EdgeIndex:
    """Boundary edges of a polygon layer, binned into EDGE_CELL_DEG cells (an edge is listed in
    every cell it passes through)."""

    def __init__(self, layer, cell_deg=const.EDGE_CELL_DEG):
        self.a_lat, self.a_lon, self.b_lat, self.b_lon, self.feature = _polygon_edges(layer)
        self.cell_deg = cell_deg
        self.rows, self.cols = round(180 / cell_deg), round(360 / cell_deg)
        edge, s_lat, s_lon = _samples(self.a_lat, self.a_lon, self.b_lat, self.b_lon, cell_deg / 2)
        cell = self._row(s_lat) * self.cols + self._col(s_lon)
        key = np.unique(cell * max(len(self.a_lat), 1) + edge)
        self.items = key % max(len(self.a_lat), 1)
        self.offsets = np.searchsorted(key // max(len(self.a_lat), 1), np.arange(self.rows * self.cols + 1))

    def _row(self, lat):
        return np.clip(np.floor((lat + 90) / self.cell_deg).astype(np.int64), 0, self.rows - 1)

    def _col(self, lon):
        return np.clip(np.floor((lon + 180) / self.cell_deg).astype(np.int64), 0, self.cols - 1)

    def within(self, lat, lon, radius_km):
        """(query, feature, km) for every feature with a boundary within radius_km of each point,
        once per pair at the nearest distance. Distances are planar in a local equirectangular
        frame around the point: exact to metres at these ranges."""
        lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        if not len(lat) or not len(self.items):
            return (np.zeros(0, dtype=np.int64),) * 2 + (np.zeros(0),)
        dlat = radius_km / KM_PER_DEG
        dlon = np.minimum(dlat / np.maximum(np.cos(np.radians(lat)), 1e-9), 180.0)
        r_lo, r_hi = self._row(lat - dlat), self._row(lat + dlat)
        c_lo = np.floor((lon - dlon + 180) / self.cell_deg).astype(np.int64)
        c_hi = np.floor((lon + dlon + 180) / self.cell_deg).astype(np.int64)
        whole = c_hi - c_lo + 1 >= self.cols
        c_lo, c_hi = np.where(whole, 0, c_lo), np.where(whole, self.cols - 1, c_hi)
        nr, nc = r_hi - r_lo + 1, c_hi - c_lo + 1
        # every (point, cell) in each point's neighbourhood
        count = nr * nc
        owner = np.repeat(np.arange(len(lat)), count)
        k = np.arange(int(count.sum())) - np.repeat(np.cumsum(count) - count, count)
        row = r_lo[owner] + k // nc[owner]
        col = (c_lo[owner] + k % nc[owner]) % self.cols
        cell = row * self.cols + col
        start, stop = self.offsets[cell], self.offsets[cell + 1]
        per_point = np.bincount(owner, weights=stop - start, minlength=len(lat))
        # blocks of whole points (owner is ascending), so each block's (point, feature) minima are final
        block = np.floor(np.cumsum(per_point) / _PAIR_BLOCK).astype(np.int64)
        cuts = np.concatenate([[0], np.flatnonzero(np.diff(block)) + 1, [len(lat)]])
        n_features = int(self.feature.max()) + 1
        out_q, out_f, out_d = [], [], []
        for p0, p1 in itertools.pairwise(cuts):
            lo, hi = np.searchsorted(owner, [p0, p1])
            q, d, f = self._pairs(lat, lon, owner[lo:hi], start[lo:hi], stop[lo:hi])
            keep = d <= radius_km
            q, d, f = q[keep], d[keep], f[keep]
            if not len(q):
                continue
            pair = q * n_features + f
            order = np.lexsort((d, pair))
            pick = order[np.flatnonzero(np.diff(pair[order], prepend=-1))]
            out_q.append(q[pick])
            out_f.append(f[pick])
            out_d.append(d[pick])
        if not out_q:
            return (np.zeros(0, dtype=np.int64),) * 2 + (np.zeros(0),)
        return np.concatenate(out_q), np.concatenate(out_f), np.concatenate(out_d)

    def _pairs(self, lat, lon, owner, start, stop):
        counts = stop - start
        q = np.repeat(owner, counts)
        e = self.items[np.arange(int(counts.sum())) - np.repeat(np.cumsum(counts) - counts - start, counts)]
        plat, plon = lat[q], lon[q]
        scale = np.cos(np.radians(plat)) * KM_PER_DEG
        ax = ((self.a_lon[e] - plon + 180) % 360 - 180) * scale
        ay = (self.a_lat[e] - plat) * KM_PER_DEG
        bx = ((self.b_lon[e] - plon + 180) % 360 - 180) * scale
        by = (self.b_lat[e] - plat) * KM_PER_DEG
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = np.clip(-(ax * dx + ay * dy) / np.where(length2 > 0, length2, 1.0), 0.0, 1.0)
        return q, np.hypot(ax + t * dx, ay + t * dy), self.feature[e]


class SampleIndex:
    """Boundary points of a polygon layer about WATER_SAMPLE_KM apart, for "nearest feature" over
    long distances; the answer is within about half the spacing of the true boundary distance."""

    def __init__(self, layer, spacing_km=const.WATER_SAMPLE_KM):
        a_lat, a_lon, b_lat, b_lon, feature = _polygon_edges(layer)
        step = spacing_km / KM_PER_DEG
        edge, s_lat, s_lon = _samples(a_lat, a_lon, b_lat, b_lon, step)
        owner = feature[edge]
        # one sample per feature per spacing-sized cell: dense coasts don't need every vertex
        qlat = np.floor((s_lat + 90) / step).astype(np.int64)
        qlon = np.floor((s_lon + 180) / step).astype(np.int64)
        key = (owner * (round(180 / step) + 2) + qlat) * (round(360 / step) + 2) + qlon
        _, first = np.unique(key, return_index=True)
        self.feature = owner[first]
        self.grid = PointGrid(s_lat[first], s_lon[first])

    def nearest(self, lat, lon, max_km):
        """(feature, km) of the nearest boundary sample to each point; -1 and inf beyond max_km."""
        idx, dist = self.grid.nearest(
            np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64), 1, max_km
        )
        idx, dist = idx[:, 0], dist[:, 0]
        return np.where(idx >= 0, self.feature[np.maximum(idx, 0)], -1), dist


class PointIndex:
    """Nearest-neighbour search over chosen rows of a point layer."""

    def __init__(self, lat, lon, rows, cell_deg=None):
        """cell_deg None lets the grid size its cells to the points' density."""
        self.rows = np.asarray(rows, dtype=np.int64)
        self.grid = PointGrid(np.asarray(lat)[self.rows], np.asarray(lon)[self.rows], cell_deg)

    def nearest(self, lat, lon, k, max_km):
        """(rows (q, k), km (q, k)), nearest first; -1 and inf where fewer than k within max_km."""
        lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        if not len(self.rows):
            return np.full((len(lat), k), -1, dtype=np.int64), np.full((len(lat), k), np.inf)
        idx, dist = self.grid.nearest(lat, lon, k, max_km)
        return np.where(idx >= 0, self.rows[np.maximum(idx, 0)], -1), dist
