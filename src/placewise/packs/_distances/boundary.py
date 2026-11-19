"""Distances from points to the boundaries of a polygon layer, exact on the sphere: each edge is a
great-circle arc, as in PolygonLayer.nearest_edge_km, and edges along ±180 (where antimeridian
features are cut) are not borders.

The index has two levels. Short edges (under _SHORT_DEG on each side, away from the poles) form
runs of up to _RUN_EDGES consecutive edges of one ring, each run inside a latitude/longitude box
padded far beyond the bulge of its arcs; a run is listed in every grid cell its box touches. A
query reads the runs in the cells of its disk, drops those whose box is farther than its radius
(a haversine bound, no trigonometry per pair), and expands the rest to their edges, each run
once however many of the disk's cells list it. Long and polar edges are listed instead in each
cell that a sample along their arc falls in, samples no more than _SPACING_KM apart, so any part
of such an arc is within half that of a listed cell (the disk is widened by that half spacing
for them). Every candidate edge then goes through a cheap triangle-inequality bound and the exact
measure. Pruning only ever drops edges that are farther than the radius, so the answers are those
of measuring every edge. Points with no border listed within a degree skip the reading entirely.

A nearest-boundary query first finds an upper bound from the nearest sample (a PointIndex over a
thinned set of samples of every arc), so its disk reaches only the stretch of boundary nearest the
point.
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo import lines

from .._geometry import planar as gm
from .._lazy import once
from .disks import Grid
from .points import PointIndex

_CELL_DEG = 0.25  # the grid edges are binned on
_SPACING_KM = _CELL_DEG * math.pi * MEAN_RADIUS_KM / 180 / 4  # arcs are sampled this often (~7 km)
_SLACK_KM = 1e-6  # so float rounding in the bounds never drops the nearest edge
_RUN_EDGES = 16  # short edges per run
_SHORT_DEG = 0.1  # an edge spanning less than this in latitude and longitude may join a run
_POLAR_DEG = 80.0  # edges reaching beyond this latitude never do
# degrees a run's box is widened by, per square degree of an edge's span: a great-circle arc of
# span L bulges at most about 0.0011 L^2 degrees past its ends' box (below _POLAR_DEG), so this is
# hundreds of times that; plus a constant far above float64 rounding
_BULGE_PAD = 0.5
_PAD_DEG = 1e-7
_BOX_SLACK = 1e-9  # relative, on the box bounds
_COVER_REACH_DEG = 0.99  # near() skips points by 1 degree cells for reaches under this


class Boundary:
    """The boundary edges of a polygon layer, ready for distance queries. Edge i runs from
    (ya[i], xa[i]) to (yb[i], xb[i]) and belongs to feature[i]; the arrays are kept, not copied."""

    def __init__(self, ya, xa, yb, xb, feature):
        self.ya, self.xa, self.yb, self.xb = ya, xa, yb, xb
        real = np.flatnonzero(~((np.abs(xa) == 180) & (np.abs(xb) == 180)))
        small = np.int32 if len(ya) < 2**31 else np.int64
        self.edge = real.astype(small)  # the edges that are borders
        self.feature = np.asarray(feature)[real].astype(np.int64)
        self._runs(self.ya[real], self.xa[real], self.yb[real], self.xb[real], real)

    def _runs(self, ya, xa, yb, xb, real):
        """Group the borders into runs, box the short ones and grid both kinds."""
        n = len(real)
        span = np.maximum(np.abs(ya - yb), np.abs(xa - xb))
        long = (span >= _SHORT_DEG) | (np.maximum(np.abs(ya), np.abs(yb)) > _POLAR_DEG)
        # a run breaks where the ring or feature does, and round every long edge (alone in its run)
        cut = np.ones(n, dtype=bool)
        cut[1:] = (
            (ya[1:] != yb[:-1])
            | (xa[1:] != xb[:-1])
            | (self.feature[1:] != self.feature[:-1])
            | (np.diff(real) != 1)
            | long[1:]
            | long[:-1]
        )
        first = np.flatnonzero(cut)
        length = np.diff(np.append(first, n))
        pieces = -(-length // _RUN_EDGES)
        owner, k = _expand(np.zeros(len(first), dtype=np.int64), pieces)
        self.run_start = first[owner] + k * _RUN_EDGES  # run r is borders run_start[r]:run_stop[r]
        self.run_stop = np.minimum(self.run_start + _RUN_EDGES, (first + length)[owner])
        start = self.run_start
        self.run_long = long[start] if n else np.zeros(0, dtype=bool)
        box = np.zeros((4, len(start)))
        if n:
            south, west, north, east = _edge_boxes(ya, xa, yb, xb)
            box[0], box[1] = np.minimum.reduceat(south, start), np.minimum.reduceat(west, start)
            box[2], box[3] = np.maximum.reduceat(north, start), np.maximum.reduceat(east, start)
        self.run_box = box  # south, west, north, east of each short run
        rows, cols = gm.grid_shape(_CELL_DEG)
        short = np.flatnonzero(~self.run_long)
        r0, r1 = (gm.cell_rows(box[i][short], _CELL_DEG, rows) for i in (0, 2))
        c0, c1 = (gm.cell_cols(box[i][short], _CELL_DEG, cols) for i in (1, 3))
        width = c1 - c0 + 1
        which, i = _expand(np.zeros(len(short), dtype=np.int64), (r1 - r0 + 1) * width)
        cells = [(r0[which] + i // width[which]) * cols + c0[which] + i % width[which]]
        items = [short[which]]
        long_runs = np.flatnonzero(self.run_long)
        self._long_reach = 0.0
        if len(long_runs):  # sampled along the arc
            sample, s_lat, s_lon = self._samples(self.run_start[long_runs])
            cell = gm.cell_rows(s_lat, _CELL_DEG, rows) * cols + gm.cell_cols(s_lon, _CELL_DEG, cols)
            m = len(long_runs)
            pair = np.unique(cell * m + sample)  # each long edge once per cell
            cells.append(pair // m)
            items.append(long_runs[pair % m])
            self._long_reach = _SPACING_KM / 2
        cells = np.concatenate(cells)
        self.grid = Grid(_CELL_DEG, cells, np.concatenate(items))
        self._cover = _coverage(cells // cols, cells % cols)

    def _covered(self, lat, lon, radius_km):
        """False for points no border can come within radius_km of: none is listed in their 1
        degree cell or the eight round it, and the radius (with the long edges' reach) spans
        under a degree of latitude and of longitude there (|dlon| <= d / cos(|lat| + d) for
        small d). Answering only the rest changes nothing, and skips layers far away cheaply."""
        reach = np.degrees((radius_km + self._long_reach + _SLACK_KM) / MEAN_RADIUS_KM)
        far = np.minimum(np.abs(lat) + reach, 90.0)
        with np.errstate(divide="ignore"):
            small = reach / np.cos(np.radians(far)) <= _COVER_REACH_DEG
        row = np.clip(np.floor(lat + 90.0), 0, 179).astype(np.int64)
        col = np.clip(np.floor(lon + 180.0), 0, 359).astype(np.int64)
        return ~small | self._cover[row, col]

    def _arcs(self, i):
        """Unit vectors of the ends of borders i (positions in self.edge), and their angles."""
        e = self.edge[i]
        a, b = lines._unit(self.ya[e], self.xa[e]), lines._unit(self.yb[e], self.xb[e])
        return a, b, _angle(a, b)

    def _samples(self, borders=None):
        """(i, lat, lon) of points along the arcs of borders (positions in self.edge; default
        all), their ends included, at most _SPACING_KM apart (spherical interpolation, so evenly
        spaced along the arc); i indexes `borders`."""
        a, b, arc = self._arcs(np.arange(len(self.edge)) if borders is None else borders)
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

    @once
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
        ok = ok[self._covered(lat[ok], lon[ok], radius_km)]
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
        reach = radius + self._long_reach + _SLACK_KM
        p_all = lines._unit(lat, lon)
        lat_reach, lon_reach = _box_reach(lat, radius)
        for q, pos in self.grid.read(lat, lon, reach):
            run = self.grid.items[pos].astype(np.int64)
            box = (side[run] for side in self.run_box)
            near = self.run_long[run] | _box_near(lat[q], lon[q], *box, lat_reach[q], lon_reach[q])
            n_runs = len(self.run_start)  # a run is read once per cell of the disk listing it
            key = np.unique(q[near] * n_runs + run[near])
            q, run = key // n_runs, key % n_runs
            which, e = _expand(self.run_start[run], self.run_stop[run])
            q = q[which]
            p = p_all[q]
            a, b, arc = self._arcs(e)
            # an arc's points are no nearer than (|pa| + |pb| - |ab|) / 2 by the triangle inequality
            bound = (_angle(p, a) + _angle(p, b) - arc) / 2 * MEAN_RADIUS_KM
            near = bound <= radius[q] + _SLACK_KM
            nearest, angle, _ = lines._nearest_on_arcs(p[near], a[near], b[near])
            yield q[near], e[near], angle * MEAN_RADIUS_KM, nearest


def _coverage(rows, cols):
    """(180, 360) bools: 1 degree cells holding or beside (round ±180 too) any of these cells of
    the _CELL_DEG grid."""
    per = round(1 / _CELL_DEG)
    cover = np.zeros((180, 360), dtype=bool)
    cover[rows // per, cols // per] = True
    cover |= np.roll(cover, 1, axis=1) | np.roll(cover, -1, axis=1)
    cover[1:] |= cover[:-1].copy()
    cover[:-1] |= cover[1:].copy()
    return cover


def _edge_boxes(ya, xa, yb, xb):
    """(south, west, north, east) of each edge's ends, widened past the bulge of its arc (for
    short edges away from the poles)."""
    pad = _BULGE_PAD * np.maximum(np.abs(ya - yb), np.abs(xa - xb)) ** 2 + _PAD_DEG
    return (
        np.minimum(ya, yb) - pad,
        np.minimum(xa, xb) - pad,
        np.maximum(ya, yb) + pad,
        np.maximum(xa, xb) + pad,
    )


def _box_reach(lat, radius_km):
    """Per point, (latitude, longitude) degrees within which a box must come for any of it to be
    within radius_km. With r that radius as an angle, every X within r of P has |lat X - lat P| <= r,
    and both latitudes within phi = |lat P| + r of the equator; hav(PX) >= cos(phi)^2 hav(dlon)
    then gives sin(dlon / 2) cos(phi) <= sin(r / 2), and sin(x / 2) >= x / pi on [0, pi] gives
    dlon <= pi sin(r / 2) / cos(phi). Both bounds are widened a hair for rounding."""
    r = np.minimum((radius_km + _SLACK_KM) / MEAN_RADIUS_KM, math.pi)
    cos_far = np.cos(np.minimum(np.radians(np.abs(lat)) + r, math.pi / 2))
    with np.errstate(divide="ignore"):
        lon_reach = np.where(cos_far > 1e-9, np.degrees(math.pi * np.sin(r / 2) / cos_far), np.inf)
    return np.degrees(r) * (1 + _BOX_SLACK), lon_reach * (1 + _BOX_SLACK)


def _box_near(lat, lon, south, west, north, east, lat_reach, lon_reach):
    """Whether each box (narrower than 180 degrees of longitude) may come within reach of its
    point: the gaps between them in latitude and in longitude (round the shorter way)."""
    lat_gap = np.maximum(np.maximum(south - lat, lat - north), 0.0)
    half = (east - west) / 2
    off = np.abs((lon - (west + half) + 180.0) % 360.0 - 180.0)
    return (lat_gap <= lat_reach) & (off - half <= lon_reach)


def _angle(u, v):
    """Angle (radians) between unit vectors, from their chord: accurate at any size."""
    chord = np.sqrt(np.sum((u - v) ** 2, axis=-1))
    return 2 * np.arcsin(np.clip(chord / 2, 0.0, 1.0))


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = np.maximum(stop - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)
