"""Distances from points to the boundaries of a polygon layer, exact on the sphere: each edge is a
great-circle arc, as in PolygonLayer.nearest_edge_km, and edges along ±180 (where antimeridian
features are cut) are not borders.

Every edge is listed in each cell of a grid that a sample along its arc falls in, samples no more
than _SPACING_KM apart, so any part of an arc is within half that of a listed cell. A query lists
the edges in the cells of its disk (widened by that half spacing), drops those that can't be near
by a cheap triangle-inequality bound, and measures the rest exactly. A nearest-boundary query
first finds an upper bound from the nearest sample (a PointIndex over a thinned set of them), so
its disk reaches only the stretch of boundary nearest the point.
"""

import math
from functools import cached_property

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo import lines

from . import _geometry as gm
from ._points import PointIndex, _Grid

_CELL_DEG = 0.25  # the grid edges are binned on
_SPACING_KM = _CELL_DEG * math.pi * MEAN_RADIUS_KM / 180 / 4  # arcs are sampled this often (~7 km)
_SLACK_KM = 1e-6  # so float rounding in the bounds never drops the nearest edge


class Boundary:
    """The boundary edges of a polygon layer, ready for distance queries. Edge i runs from
    (ya[i], xa[i]) to (yb[i], xb[i]) and belongs to feature[i]; the arrays are kept, not copied."""

    def __init__(self, ya, xa, yb, xb, feature):
        self.ya, self.xa, self.yb, self.xb = ya, xa, yb, xb
        real = np.flatnonzero(~((np.abs(xa) == 180) & (np.abs(xb) == 180)))
        small = np.int32 if len(ya) < 2**31 else np.int64
        self.edge = real.astype(small)  # the edges that are borders
        self.feature = np.asarray(feature)[real].astype(np.int64)
        sample, s_lat, s_lon = self._samples()
        rows, cols = gm.grid_shape(_CELL_DEG)
        cell = gm.cell_rows(s_lat, _CELL_DEG, rows) * cols + gm.cell_cols(s_lon, _CELL_DEG, cols)
        n = max(len(real), 1)
        pair = np.unique(cell * n + sample)  # each border once per cell
        self.grid = _Grid(_CELL_DEG, pair // n, pair % n)

    def _arcs(self, i):
        """Unit vectors of the ends of borders i (positions in self.edge), and their angles."""
        e = self.edge[i]
        a, b = lines._unit(self.ya[e], self.xa[e]), lines._unit(self.yb[e], self.xb[e])
        return a, b, _angle(a, b)

    def _samples(self):
        """(border, lat, lon) of points along every arc, its ends included, at most _SPACING_KM
        apart (spherical interpolation, so evenly spaced along the arc)."""
        a, b, arc = self._arcs(np.arange(len(self.edge)))
        n = np.ceil(arc * MEAN_RADIUS_KM / _SPACING_KM).astype(np.int64) + 1
        edge = np.repeat(np.arange(len(n)), n)
        t = (np.arange(int(n.sum())) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(np.maximum(n - 1, 1), n)
        theta = arc[edge]
        sin_t = np.sin(theta)
        short = sin_t < 1e-12  # a zero-length edge: just its start
        with np.errstate(invalid="ignore", divide="ignore"):
            wa = np.where(short, 1 - t, np.sin((1 - t) * theta) / sin_t)
            wb = np.where(short, t, np.sin(t * theta) / sin_t)
        v = wa[:, None] * a[edge] + wb[:, None] * b[edge]
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        lat = np.degrees(np.arcsin(np.clip(v[:, 2], -1.0, 1.0)))
        lon = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
        return edge, lat, lon

    @cached_property
    def _sample_index(self):
        """One sample per feature per spacing-sized cell: enough for an upper bound."""
        edge, s_lat, s_lon = self._samples()
        step = _SPACING_KM / (math.pi * MEAN_RADIUS_KM / 180)
        rows, cols = gm.grid_shape(step)
        cell = gm.cell_rows(s_lat, step, rows) * cols + gm.cell_cols(s_lon, step, cols)
        _, first = np.unique(self.feature[edge] * (rows * cols) + cell, return_index=True)
        return PointIndex(s_lat[first], s_lon[first])

    def near(self, lat, lon, radius_km):
        """(point, feature, km), one row per pair whose boundary comes within radius_km, at the
        nearest distance, sorted by point then feature. lat, lon: flat, normalised (NaN: none)."""
        ok = np.flatnonzero(np.isfinite(lat))
        radius = np.full(len(ok), float(radius_km))
        out_q, out_f, out_d = [], [], []
        for q, e, d, _ in self._measure(lat[ok], lon[ok], radius):
            keep = d <= radius_km
            out_q.append(ok[q[keep]])
            out_f.append(self.feature[e[keep]])
            out_d.append(d[keep])
        q, f, d = (
            np.concatenate(x) if x else np.zeros(0, dtype=t)
            for x, t in ((out_q, np.int64), (out_f, np.int64), (out_d, float))
        )
        # the nearest distance per (point, feature)
        order = np.lexsort((d, f, q))
        q, f, d = q[order], f[order], d[order]
        first = np.flatnonzero((np.diff(q, prepend=-1) != 0) | (np.diff(f, prepend=-1) != 0))
        return q[first], f[first], d[first]

    def nearest(self, lat, lon, max_km):
        """(feature, km, lat, lon) of the nearest boundary point to each query point, ties to the
        lower feature; -1, inf, NaN, NaN where none is within max_km (None: no limit)."""
        n = len(lat)
        feature, dist = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
        at = np.full((n, 3), np.nan)
        ok = np.flatnonzero(np.isfinite(lat))
        if len(ok) and len(self.feature):
            # every boundary point is within half a spacing of a sample, and a sample is on it
            reach = None if max_km is None else max_km + _SPACING_KM / 2
            _, upper = self._sample_index.nearest(lat[ok], lon[ok], k=1, max_km=reach)
            upper = np.atleast_1d(upper)
            found = np.isfinite(upper)
            ok, upper = ok[found], upper[found]
            best_d = np.full(len(ok), np.inf)
            best_f = np.full(len(ok), np.iinfo(np.int64).max)
            for q, e, d, nearest in self._measure(lat[ok], lon[ok], upper):
                f = self.feature[e]
                order = np.lexsort((f, d, q))  # per point: nearest, then lowest feature
                pick = order[np.flatnonzero(np.diff(q[order], prepend=-1))]
                q, f, d, nearest = q[pick], f[pick], d[pick], nearest[pick]
                better = (d < best_d[q]) | ((d == best_d[q]) & (f < best_f[q]))
                q, f, d, nearest = q[better], f[better], d[better], nearest[better]
                best_d[q], best_f[q], at[ok[q]] = d, f, nearest
            feature[ok], dist[ok] = best_f, best_d
            if max_km is not None:
                far = dist > max_km
                feature[far], dist[far], at[far] = -1, np.inf, np.nan
        at_lat = np.degrees(np.arcsin(np.clip(at[:, 2], -1.0, 1.0)))
        at_lon = np.degrees(np.arctan2(at[:, 1], at[:, 0]))
        return feature, dist, at_lat, at_lon

    def _measure(self, lat, lon, radius):
        """Yield (point, edge, km, nearest point as a unit vector) for the edges that may come
        within each point's radius (all that do, and some that don't)."""
        if not len(lat) or not len(self.feature):
            return
        reach = radius + _SPACING_KM / 2 + _SLACK_KM
        p_all = lines._unit(lat, lon)
        for q, pos in self.grid.read(lat, lon, reach):
            e = self.grid.items[pos].astype(np.int64)
            p = p_all[q]
            a, b, arc = self._arcs(e)
            # an arc's points are no nearer than (|pa| + |pb| - |ab|) / 2 by the triangle inequality
            bound = (_angle(p, a) + _angle(p, b) - arc) / 2 * MEAN_RADIUS_KM
            near = bound <= radius[q] + _SLACK_KM
            nearest, angle, _ = lines._nearest_on_arcs(p[near], a[near], b[near])
            yield q[near], e[near], angle * MEAN_RADIUS_KM, nearest


def _angle(u, v):
    """Angle (radians) between unit vectors, from their chord: accurate at any size."""
    chord = np.sqrt(np.sum((u - v) ** 2, axis=-1))
    return 2 * np.arcsin(np.clip(chord / 2, 0.0, 1.0))
