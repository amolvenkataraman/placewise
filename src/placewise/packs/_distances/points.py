"""Nearest-neighbour and radius search over points on the sphere, with exact haversine distances.

Points are sorted by grid cell (id = row * cols + col), so the points of any run of cells along a
row are one contiguous slice. Every search reads a *disk* (disks.py): for each grid row the disk
crosses, the run of cells covering its width there. Listing a disk costs two table lookups per row,
and the listing holds every point within the radius plus a rim of at most a cell. Big disks are
drawn on coarser grids (each twice the last, built on first use), so a disk crosses a few dozen
rows however big it is.

A k-nearest query reads a small disk round it (half a cell, less where its cell is crowded),
which in dense areas lists its k nearest. Where that lists fewer than k points it finds, by
counting alone, a radius whose disk lists k: growing it fourfold at a time, then halving the gap
while the disk would list many more points than needed. Counting costs per row, not per point, so
a query a continent away from its nearest point stays cheap. It then reads that disk. The answer
is exact once the k-th nearest read lies within the radius read; otherwise one more read out to
that k-th distance (an upper bound on the true one) settles it. Every step works in batches of
bounded size, so memory stays bounded however remote the queries.

(The first version grew square blocks of cells and read every point in each: a query far out at
sea read whole continents, 25 s and 13 GB for 20k such queries on the world's cities.)
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.packs import POINT_CELL_DEGS, POINT_CELL_TARGET
from placewise.geo import haversine, validate

from .._geometry import planar as gm
from .._lazy import Guarded
from .disks import TABLE_CELLS, Grid

_HALF_TURN_KM = math.pi * MEAN_RADIUS_KM  # no two points on the sphere are farther apart
# up to this k, the k best are picked by repeated minima rather than a full sort
_SELECT_K = 8
_NO_INDEX = np.iinfo(np.int64).max
# the search for a radius holding k points: start at this many cells, grow by this factor, then
# halve the gap between too few and enough this many times (each narrows the rim of extra points
# read, for the price of one more count)
_FIRST_RADIUS_CELLS = 0.5
_FIRST_POINTS = 4  # points per k the first disk aims for where the query's cell is crowded
_GROWTH = 4.0
_BISECT_STEPS = 4
_READ_FREELY = 32  # points beyond k a disk may list before narrowing it is worth a count
# disks are drawn on a grid with cells of about radius / this, coarser grids for bigger disks
_ROWS_PER_RADIUS = 8
_COARSEST_DEG = 30.0


def choose_cell_deg(lat, lon):
    """The coarsest grid where a point's cell holds at most POINT_CELL_TARGET points on average.
    Averaged over points rather than cells, so dense clusters (cities) get small cells."""
    for cell_deg in sorted(POINT_CELL_DEGS, reverse=True):
        rows, cols = gm.grid_shape(cell_deg)
        ids = gm.cell_rows(lat, cell_deg, rows) * cols + gm.cell_cols(lon, cell_deg, cols)
        if rows * cols <= TABLE_CELLS:  # counting is cheaper than sorting (empty cells add 0)
            counts = np.bincount(ids, minlength=rows * cols).astype(np.float64)
        else:
            counts = np.unique(ids, return_counts=True)[1].astype(np.float64)
        if np.sum(counts * counts) <= POINT_CELL_TARGET * len(lat):
            return cell_deg
    return min(POINT_CELL_DEGS)


class PointIndex(Guarded):
    """Exact k-nearest and radius search over a fixed set of points (WGS84 degrees), with
    haversine distances in km on the mean-radius sphere.

        index = PointIndex(lats, lons)
        idx, km = index.nearest(qlats, qlons, k=3, max_km=50)
        idx, km = index.within(lat, lon, 25)

    Indexes are positions in the arrays given. `cell_deg` (default: sized to the points' density)
    only affects speed, never answers."""

    def __init__(self, lat, lon, cell_deg=None):
        super().__init__()
        lat = np.array(lat, dtype=np.float64).ravel()
        lon = np.array(lon, dtype=np.float64).ravel()
        if lat.shape != lon.shape:
            raise ValueError(f"{len(lat)} latitudes but {len(lon)} longitudes")
        if len(lat):
            validate(lat, lon)
        if cell_deg is not None and not 0 < cell_deg <= 180:
            raise ValueError("cell_deg must be in (0, 180]")
        lat.flags.writeable = lon.flags.writeable = False
        self.lat, self.lon = lat, lon
        self.cell_deg = float(cell_deg or (choose_cell_deg(lat, lon) if len(lat) else 90.0))
        # the grid at cell_deg, then coarser ones (each twice the last) for far-reaching disks,
        # built when first needed
        self._grids = [Grid.of_points(lat, lon, self.cell_deg)]
        # the finest grid's points' coordinates in its own order, for fast reads
        self._slat, self._slon = lat[self._grids[0].items], lon[self._grids[0].items]
        self._n_levels = 1 + max(0, math.ceil(math.log2(_COARSEST_DEG / self.cell_deg)))

    def __len__(self):
        return len(self.lat)

    def __repr__(self):
        return f"<PointIndex {len(self)} points, {self.cell_deg:g} deg cells>"

    # -- public API -------------------------------------------------------------------------------

    def nearest(self, lat, lon, k=1, max_km=None):
        """(indexes, distances_km) of the k nearest points to each query point, nearest first, ties
        to the lower index; -1 and inf where there are fewer than k (within max_km). Shapes: the
        query's, plus a trailing k axis when k > 1; plain int and float for a scalar query with
        k=1. Longitudes outside ±180 wrap; non-finite or out-of-range points find nothing."""
        if k < 1:
            raise ValueError("k must be at least 1")
        lat, lon = np.broadcast_arrays(np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64))
        shape = lat.shape
        flat_lat, flat_lon = gm.normalise(lat.ravel(), lon.ravel())
        idx, dist = self._nearest(flat_lat, flat_lon, int(k), max_km)
        if k > 1:
            return idx.reshape((*shape, k)), dist.reshape((*shape, k))
        idx, dist = idx[:, 0].reshape(shape), dist[:, 0].reshape(shape)
        return (int(idx), float(dist)) if not shape else (idx, dist)

    def within(self, lat, lon, radius_km):
        """(indexes, distances_km) of every point within radius_km of one point, nearest first,
        ties to the lower index."""
        flat_lat, flat_lon = gm.normalise(np.array([float(lat)]), np.array([float(lon)]))
        radius_km = float(radius_km)
        if not len(self.lat) or not np.isfinite(flat_lat[0]) or not radius_km >= 0:
            return np.zeros(0, dtype=np.int64), np.zeros(0)
        found_i, found_d = [np.zeros(0, dtype=np.int64)], [np.zeros(0)]
        for q, index, plat, plon in self._read(flat_lat, flat_lon, np.array([min(radius_km, _HALF_TURN_KM)])):
            d = haversine(flat_lat[q], flat_lon[q], plat, plon)
            keep = d <= radius_km
            found_i.append(index[keep])
            found_d.append(d[keep])
        index, d = np.concatenate(found_i), np.concatenate(found_d)
        order = np.lexsort((index, d))
        return index[order], d[order]

    # -- k nearest --------------------------------------------------------------------------------

    def _nearest(self, lat, lon, k, max_km):
        """(q, k) indexes and distances for flat, normalised query arrays (NaN: none)."""
        best_i = np.full((len(lat), k), -1, dtype=np.int64)
        best_d = np.full((len(lat), k), np.inf)
        todo = np.flatnonzero(np.isfinite(lat) & np.isfinite(lon))
        cap = _HALF_TURN_KM if max_km is None else min(float(max_km), _HALF_TURN_KM)
        if not len(self.lat) or not len(todo) or not cap >= 0:
            return best_i, best_d
        limit = np.inf if max_km is None else float(max_km)
        qlat, qlon = lat[todo], lon[todo]

        # 1. read a small disk round each query, which in dense areas settles it: half a cell,
        # less where the query's own cell holds many more points than k
        hi = np.minimum(self._first_radius(qlat, qlon, k), cap)
        count = self._fill(best_i, best_d, todo, qlat, qlon, hi, k, limit)

        # 2. where it lists fewer than k points, find a radius whose disk lists k, by counting
        # alone (growing it, then narrowing the gap), and read that disk
        short = np.flatnonzero((count < k) & (hi < cap))
        if len(short):
            s_lat, s_lon, lo, s_hi = qlat[short], qlon[short], hi[short], hi[short].copy()
            s_count = count[short]
            grow = np.arange(len(short))
            while len(grow):
                lo[grow], s_hi[grow] = s_hi[grow], np.minimum(s_hi[grow] * _GROWTH, cap)
                grow = grow[s_hi[grow] < cap]  # a disk at the cap is read whatever it holds
                s_count[grow] = self._count(s_lat[grow], s_lon[grow], s_hi[grow])
                grow = grow[s_count[grow] < k]
            # narrowing pays only where the disk lists many more points than needed
            for _ in range(_BISECT_STEPS):
                narrow = np.flatnonzero((s_count > _READ_FREELY + k) & (s_count >= k) & (s_hi < cap))
                if not len(narrow):
                    break
                mid = (lo[narrow] + s_hi[narrow]) / 2
                c = self._count(s_lat[narrow], s_lon[narrow], mid)
                enough = c >= k
                s_hi[narrow[enough]], s_count[narrow[enough]] = mid[enough], c[enough]
                lo[narrow[~enough]] = mid[~enough]
            # read on the grid it was counted on, so at least k points come back
            rows = todo[short]
            best_i[rows], best_d[rows] = -1, np.inf
            self._fill(best_i, best_d, rows, s_lat, s_lon, s_hi, k, limit)
            hi[short] = s_hi

        # 3. the answer is exact where the k-th nearest lies within the radius read (or that is
        # the cap); otherwise read once more out to the k-th distance found, an upper bound
        kth = best_d[todo, k - 1]
        again = np.flatnonzero((kth > hi) & (hi < cap))
        if len(again):
            rows = todo[again]
            best_i[rows], best_d[rows] = -1, np.inf
            self._fill(best_i, best_d, rows, qlat[again], qlon[again], np.minimum(kth[again], cap), k, limit)
        return best_i, best_d

    def _first_radius(self, lat, lon, k):
        """km: half a cell, shrunk where the query's own cell holds many more points than k."""
        grid = self._grids[0]
        rho = np.full(len(lat), grid.km * _FIRST_RADIUS_CELLS)
        if grid.first is not None:
            cell = gm.cell_rows(lat, grid.cell_deg, grid.rows) * grid.cols + gm.cell_cols(
                lon, grid.cell_deg, grid.cols
            )
            in_cell = (grid.first[cell + 1] - grid.first[cell]).astype(np.float64)
            # a disk's points grow with its area: aim for a few times k
            rho *= np.clip(np.sqrt(_FIRST_POINTS * k / np.maximum(in_cell, 1.0)), 1 / 16, 1.0)
        return rho

    def _fill(self, best_i, best_d, rows, lat, lon, rho, k, limit):
        """Fold every point listed for each query's disk of rho km into its k best (best_*[rows]);
        returns how many points were listed per query."""
        listed = np.zeros(len(lat), dtype=np.int64)
        for q, index, plat, plon in self._read(lat, lon, rho):
            listed += np.bincount(q, minlength=len(lat))
            d = haversine(lat[q], lon[q], plat, plon)
            # only points nearer than a query's current k-th (and within the limit) can count
            keep = d <= np.minimum(best_d[rows[q], k - 1], limit)
            _merge(best_i, best_d, rows, q[keep], index[keep], d[keep], k)
        return listed

    # -- disks, each on the grid that suits its radius --------------------------------------------

    def _levels(self, rho):
        """The grid level for disks of rho km: cells of at most rho / _ROWS_PER_RADIUS, so a disk
        crosses a few dozen rows however big it is (and level 0 for small disks)."""
        ratio = rho / (_ROWS_PER_RADIUS * self._grids[0].km)
        with np.errstate(divide="ignore"):
            level = np.floor(np.log2(np.maximum(ratio, 1.0))).astype(np.int64)
        return np.minimum(level, self._n_levels - 1)

    def _grid(self, level):
        if len(self._grids) <= level:
            with self._lock:  # each level once, in order, however many threads ask
                while len(self._grids) <= level:
                    self._grids.append(Grid.of_points(self.lat, self.lon, self._grids[-1].cell_deg * 2))
        return self._grids[level]

    def _by_level(self, rho):
        """(level, positions) of the queries to handle on each grid."""
        if not len(rho):
            return []
        level = self._levels(rho)
        if (level == level[0]).all():
            return [(int(level[0]), slice(None))]
        return [(int(v), np.flatnonzero(level == v)) for v in np.unique(level)]

    def _count(self, lat, lon, rho):
        """Points listed for the disk of rho km round each query (at least those within rho)."""
        count = np.zeros(len(lat), dtype=np.int64)
        for level, at in self._by_level(rho):
            count[at] = self._grid(level).count(lat[at], lon[at], rho[at])
        return count

    def _read(self, lat, lon, rho):
        """Yield (query, point index, lat, lon) for every point listed for each query's disk of
        rho km, each pair once, in batches of about disks._PAIR_BUDGET."""
        for level, at in self._by_level(rho):
            queries = np.arange(len(lat))[at]
            grid = self._grid(level)
            for q, pos in grid.read(lat[at], lon[at], rho[at]):
                index = grid.items[pos].astype(np.int64)
                if level == 0:
                    yield queries[q], index, self._slat[pos], self._slon[pos]
                else:
                    yield queries[q], index, self.lat[index], self.lon[index]


def _merge(best_i, best_d, rows, qpos, index, d, k):
    """Fold new (query, point, distance) candidates into each query's k best (best_*[rows[qpos]]),
    nearest first, equal distances to the lower index."""
    if not len(qpos):
        return
    present = np.bincount(qpos, minlength=len(rows)) > 0  # only these queries can change
    target = rows[present]
    nq = len(target)
    old_i, old_d = best_i[target].ravel(), best_d[target].ravel()
    filled = np.flatnonzero(old_i >= 0)  # empty slots (-1, inf) need no sorting
    q = np.concatenate([filled // k, (np.cumsum(present) - 1)[qpos]])
    i = np.concatenate([old_i[filled], index])
    dd = np.concatenate([old_d[filled], d])
    new_i, new_d = np.full((nq, k), -1, dtype=np.int64), np.full((nq, k), np.inf)
    if k > _SELECT_K:
        order = _sort_by_query_distance_index(q, dd, i)
        q, i, dd = q[order], i[order], dd[order]
        rank = np.arange(len(q)) - np.searchsorted(q, np.arange(nq))[q]
        top = (rank < k) & (i >= 0)
        new_i[q[top], rank[top]], new_d[q[top], rank[top]] = i[top], dd[top]
    else:
        # k rounds of "take each query's minimum" beat sorting everything when k is small
        order = np.argsort(q, kind="stable")
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
    best_i[target], best_d[target] = new_i, new_d


def _sort_by_query_distance_index(q, d, i):
    """np.lexsort((i, d, q)), faster: distances become ranks, so (query, rank) is one integer key;
    the rare runs of equal (query, distance) are then put in index order."""
    n = len(q)
    rank = np.empty(n, dtype=np.int64)
    rank[np.argsort(d, kind="stable")] = np.arange(n)
    order = np.argsort(q * n + rank, kind="stable")
    sq, sd = q[order], d[order]
    tie = np.flatnonzero((sq[1:] == sq[:-1]) & (sd[1:] == sd[:-1]))
    if len(tie):
        runs = np.unique(np.concatenate([tie, tie + 1]))  # positions in runs of equal keys
        sub = order[runs]
        order[runs] = sub[np.lexsort((i[sub], d[sub], q[sub]))]
    return order
