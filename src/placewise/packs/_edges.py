"""Distances from points to the boundary of a feature given for each (PolygonLayer.nearest_edge_km),
exact on the sphere, without measuring every edge of the feature.

The edges of each ring, in runs of consecutive ones, lie inside a cap (a centre and an angular
radius) that bounds the distance from a point to any of them from both sides; runs near each other
(consecutive along a Z-order curve of their centres) form groups inside bigger caps. A point looks
only at the groups, then the runs, whose lower bound beats the least upper bound found among them;
of their edges it measures those that can beat its nearest vertex there (by the triangle
inequality, as measuring every edge does). Those always include its nearest edge, so the answer is
the minimum of the same numbers, computed by the same expressions, as measuring every edge gives.

Caps are made for a feature when it is first asked about, and kept for all of a layer's features
in one set of arrays, so a batch of points asking about different features is answered at once.
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo import lines

from ._lazy import Guarded

_RUN_EDGES = (8, 64)  # edges per run: a quarter of the square root of the feature's count, within these
_GROUP_RUNS = 32
_SLACK = 1e-9  # radians added to every bound, far above the rounding of their angles
_PAIRS = 1 << 19  # (query, group), (query, run) or (query, edge) pairs handled at once


class EdgeCaps(Guarded):
    """The caps of a polygon layer's features: edge e runs from (ya[e], xa[e]) to (yb[e], xb[e]),
    and rings(f) gives the vertex offsets of feature f's rings (its edges are rings[0]:rings[-1]).
    Safe to share between threads: adding caps and reading them hold one lock."""

    def __init__(self, ya, xa, yb, xb, rings, count):
        super().__init__()
        self.ya, self.xa, self.yb, self.xb = ya, xa, yb, xb
        self._rings = rings
        self.g_start = np.full(count, -1, dtype=np.int64)  # feature f's groups: g_start[f]:g_stop[f]
        self.g_stop = np.full(count, -1, dtype=np.int64)
        self.r_first = self.r_end = np.zeros(0, dtype=np.int64)  # each run's edges
        self.r_centre, self.r_radius = np.zeros((0, 3)), np.zeros(0)
        self.g_run_start = self.g_run_stop = np.zeros(0, dtype=np.int64)  # each group's runs
        self.g_centre, self.g_radius = np.zeros((0, 3)), np.zeros(0)

    def add(self, features):
        """Make the caps of these features (those without them yet)."""
        with self._lock:
            self._add(features)

    def _add(self, features):
        new = np.unique(np.asarray(features, dtype=np.int64))
        new = new[self.g_start[new] < 0].tolist()
        if not new:
            return
        runs, groups = [], []
        n_runs, n_groups = len(self.r_first), len(self.g_centre)
        for f in new:
            run, group = _caps(self.ya, self.xa, self.yb, self.xb, self._rings(f))
            group[0][:] += n_runs
            group[1][:] += n_runs
            self.g_start[f], self.g_stop[f] = n_groups, n_groups + len(group[2])
            n_runs, n_groups = n_runs + len(run[0]), n_groups + len(group[2])
            runs.append(run)
            groups.append(group)
        self.r_first, self.r_end, self.r_centre, self.r_radius = (
            np.concatenate([old, *(r[k] for r in runs)])
            for k, old in enumerate((self.r_first, self.r_end, self.r_centre, self.r_radius))
        )
        self.g_run_start, self.g_run_stop, self.g_centre, self.g_radius = (
            np.concatenate([old, *(g[k] for g in groups)])
            for k, old in enumerate((self.g_run_start, self.g_run_stop, self.g_centre, self.g_radius))
        )

    def km(self, lat, lon, feature):
        """Distance (km) from each point (flat arrays of finite degrees, |lat| <= 90) to the
        boundary of its own feature (an index per point); inf where it has no border edges."""
        n = len(lat)
        best = np.full(n, np.inf)
        if not n:
            return best
        with self._lock:
            self._add(feature)
            return self._km(best, lat, lon, feature)

    def _km(self, best, lat, lon, feature):
        n = len(lat)
        p_all = lines._unit(lat, lon)
        gs, ge = self.g_start[feature], self.g_stop[feature]
        for b0, b1 in _slices(ge - gs, _PAIRS):
            owner, g = _expand(gs[b0:b1], ge[b0:b1])
            q, g = _closest(p_all, owner + b0, g, self.g_centre, self.g_radius, n)
            for s0, s1 in _slices(self.g_run_stop[g] - self.g_run_start[g], _PAIRS):
                owner, r = _expand(self.g_run_start[g[s0:s1]], self.g_run_stop[g[s0:s1]])
                qr, r = _closest(p_all, q[s0:s1][owner], r, self.r_centre, self.r_radius, n)
                self._measure(best, lat, lon, qr, r)
        return best

    def _measure(self, best, lat, lon, q, run):
        """Fold into best the distances to the edges of these (query, run) pairs that can matter."""
        for s0, s1 in _slices(self.r_end[run] - self.r_first[run], _PAIRS):
            owner, e = _expand(self.r_first[run[s0:s1]], self.r_end[run[s0:s1]])
            keep = _real(self.xa[e], self.xb[e])
            qi, e = q[s0:s1][owner[keep]], e[keep]
            # the same expressions as measuring every edge, so the same numbers
            p = lines._unit(lat[qi], lon[qi])
            a, b = lines._unit(self.ya[e], self.xa[e]), lines._unit(self.yb[e], self.xb[e])
            to_a = _angle(p, a)
            vertex = np.full(len(lat), np.inf)
            np.minimum.at(vertex, qi, to_a)
            near = to_a - _angle(a, b) <= vertex[qi] + _SLACK
            dist = lines._nearest_on_arcs(p[near], a[near], b[near])[1] * MEAN_RADIUS_KM
            np.minimum.at(best, qi[near], dist)


def _closest(p_all, q, cap, centre, radius, n):
    """The (query, cap) pairs whose cap's lower bound beats the query's least upper bound."""
    angle = _angle(p_all[q], centre[cap])
    upper = np.full(n, np.inf)
    np.minimum.at(upper, q, angle + radius[cap])
    keep = angle - radius[cap] <= upper[q] + _SLACK
    return q[keep], cap[keep]


def _caps(ya, xa, yb, xb, rings):
    """One feature's runs (first edge, end, centre, radius) and groups (first run, end run,
    centre, radius), runs numbered from 0, only runs with border edges."""
    rings = np.asarray(rings, dtype=np.int64)
    start, stop = int(rings[0]), int(rings[-1])
    size = int(np.clip(round(math.sqrt(max(stop - start, 1)) / 4), *_RUN_EDGES))
    r0, r1 = rings[:-1][rings[1:] > rings[:-1]], rings[1:][rings[1:] > rings[:-1]]
    ring, k = _expand(np.zeros(len(r0), dtype=np.int64), -(-(r1 - r0) // size))
    first = r0[ring] + k * size  # the runs cover start:stop in order
    end = np.minimum(first + size, r1[ring])
    if not len(first):
        empty = np.zeros(0, dtype=np.int64)
        return (empty, empty, np.zeros((0, 3)), np.zeros(0)), (empty, empty, np.zeros((0, 3)), np.zeros(0))
    a, b = lines._unit(ya[start:stop], xa[start:stop]), lines._unit(yb[start:stop], xb[start:stop])
    real = _real(xa[start:stop], xb[start:stop])
    at = first - start
    run = np.repeat(np.arange(len(first)), end - first)
    centre = _centres(np.add.reduceat(np.where(real[:, None], a + b, 0.0), at), a[at])
    reach = np.where(real, np.maximum(_angle(centre[run], a), _angle(centre[run], b)), 0.0)
    radius = np.maximum.reduceat(reach, at) + _SLACK
    # a cap under a quarter turn holds the minor arcs between its points; wider ones bound nothing
    radius = np.where(radius < math.pi / 2, radius, math.pi)
    has = np.add.reduceat(real, at) > 0
    first, end, centre, radius = first[has], end[has], centre[has], radius[has]
    order = np.argsort(_z_order(centre), kind="stable")
    first, end, centre, radius = first[order], end[order], centre[order], radius[order]
    g_at = np.arange(0, len(first), _GROUP_RUNS)
    g_end = np.minimum(g_at + _GROUP_RUNS, len(first))
    if not len(g_at):
        return (first, end, centre, radius), (g_at, g_end, np.zeros((0, 3)), np.zeros(0))
    g_centre = _centres(np.add.reduceat(centre, g_at), centre[g_at])
    g_of = np.repeat(np.arange(len(g_at)), g_end - g_at)
    # every point of a run's cap is within this of its group's centre
    g_radius = np.maximum.reduceat(_angle(g_centre[g_of], centre) + radius, g_at) + _SLACK
    return (first, end, centre, radius), (g_at, g_end, g_centre, g_radius)


def _centres(total, fallback):
    """Unit vectors along each summed row; `fallback`'s where a sum vanishes (any centre bounds)."""
    norm = np.linalg.norm(total, axis=1, keepdims=True)
    return np.where(norm > 1e-9, total / np.where(norm > 0, norm, 1.0), fallback)


def _z_order(v):
    """A Z-order (Morton) key of unit vectors' latitude and longitude, 16 bits each."""
    lat = np.arcsin(np.clip(v[:, 2], -1.0, 1.0))
    lon = np.arctan2(v[:, 1], v[:, 0])
    y = np.clip((lat / math.pi + 0.5) * 65535, 0, 65535).astype(np.uint64)
    x = np.clip((lon / (2 * math.pi) + 0.5) * 65535, 0, 65535).astype(np.uint64)
    return _spread(x) | (_spread(y) << np.uint64(1))


def _spread(v):
    """The 16 low bits of v moved to the even bit positions."""
    for shift, mask in ((8, 0x00FF00FF), (4, 0x0F0F0F0F), (2, 0x33333333), (1, 0x55555555)):
        v = (v | (v << np.uint64(shift))) & np.uint64(mask)
    return v


def _angle(u, v):
    """Angle (radians) between unit vectors, from their chord: accurate at any size."""
    chord = np.sqrt(np.sum((u - v) ** 2, axis=-1))
    return 2 * np.arcsin(np.clip(chord / 2, 0.0, 1.0))


def _real(xa, xb):
    """Edges that are borders: not along ±180, where antimeridian features are cut."""
    return ~((np.abs(xa) == 180) & (np.abs(xb) == 180))


def _slices(sizes, budget):
    """(start, stop) slices of consecutive items whose sizes add up to about budget each."""
    if not len(sizes):
        return []
    group = np.maximum(np.cumsum(sizes) - 1, 0) // budget
    cuts = (np.flatnonzero(np.diff(group)) + 1).tolist()
    return list(zip([0, *cuts], [*cuts, len(sizes)], strict=True))


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = np.maximum(stop - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)
