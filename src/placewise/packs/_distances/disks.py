"""Disks on a latitude/longitude grid: items (points, or boundary edges) sorted by the cell they
lie in, and for a disk of some radius round each query, the runs of sorted items covering it.

For each grid row a disk crosses, the run of cells covering its width there is one contiguous slice
of the sorted items, so listing a disk costs two table lookups per row, and the listing holds every
item within the radius plus a rim of at most a cell. PointIndex (points.py) and Boundary
(boundary.py) search their items through these grids.
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM

from .._geometry import planar as gm

_KM_PER_DEG = math.pi * MEAN_RADIUS_KM / 180
# disks are widened by these so float rounding can never leave out a point at the radius
_MARGIN_RAD = 1e-9
_MARGIN_DEG = 1e-9
# work per batch: (query, row) pairs while listing disks, (query, point) pairs while reading them
_ROW_BUDGET = 1 << 19
_PAIR_BUDGET = 1 << 20
# grids up to this many cells keep each cell's first point in a table instead of binary search
TABLE_CELLS = 1 << 22


class Grid:
    """Items (points, or boundary edges) sorted by the cell of a grid they lie in, and the disks
    drawn on that grid. An item may be listed in several cells."""

    def __init__(self, cell_deg, ids, items=None):
        """ids: the cell (row * cols + col) of each entry; items: the item each entry is for
        (default: entry i is item i)."""
        self.cell_deg = cell_deg
        self.km = cell_deg * _KM_PER_DEG
        self.rows, self.cols = gm.grid_shape(cell_deg)
        order = np.argsort(ids, kind="stable")
        items = order if items is None else np.asarray(items)[order]
        small = np.int32 if len(ids) < 2**31 else np.int64
        self.items = items.astype(small)
        # each cell's first entry in sorted order, so a run of cells is two lookups; very fine
        # grids binary-search the sorted cell ids instead
        self.ids, self.first = ids[order], None
        n_cells = self.rows * self.cols
        if n_cells <= TABLE_CELLS:
            first = np.zeros(n_cells + 1, dtype=np.int64)  # entries in cells before each cell
            np.cumsum(np.bincount(ids, minlength=n_cells), out=first[1:])
            self.ids, self.first = None, first.astype(small)
        # sine and cosine of every row edge, for the disks' widths
        edge = np.radians(np.minimum(-90.0 + np.arange(self.rows + 1) * cell_deg, 90.0))
        self.sin_edge, self.cos_edge = np.sin(edge), np.cos(edge)

    @classmethod
    def of_points(cls, lat, lon, cell_deg):
        rows, cols = gm.grid_shape(cell_deg)
        return cls(cell_deg, gm.cell_rows(lat, cell_deg, rows) * cols + gm.cell_cols(lon, cell_deg, cols))

    def count(self, lat, lon, rho):
        """Entries listed for the disk of rho km round each query (at least those within rho)."""
        count = np.zeros(len(lat), dtype=np.int64)
        for b0, b1 in self._row_batches(lat, rho):
            owner, start, stop = self.spans(lat[b0:b1], lon[b0:b1], rho[b0:b1])
            count[b0:b1] = np.bincount(owner, weights=stop - start, minlength=b1 - b0).astype(np.int64)
        return count

    def read(self, lat, lon, rho):
        """Yield (query, sorted position) for every entry listed for each query's disk of rho km,
        in batches of about _PAIR_BUDGET; self.items[position] is the item."""
        for b0, b1 in self._row_batches(lat, rho):
            owner, start, stop = self.spans(lat[b0:b1], lon[b0:b1], rho[b0:b1])
            used = np.flatnonzero(stop > start)
            owner, start, stop = owner[used] + b0, start[used], stop[used]
            for s0, s1 in _batches(stop - start, _PAIR_BUDGET):
                which, pos = _expand(start[s0:s1], stop[s0:s1])
                yield owner[s0:s1][which], pos

    def _row_range(self, lat, rho):
        dlat = np.degrees(rho / MEAN_RADIUS_KM + _MARGIN_RAD) + _MARGIN_DEG
        return gm.cell_rows(lat - dlat, self.cell_deg, self.rows), gm.cell_rows(
            lat + dlat, self.cell_deg, self.rows
        )

    def _row_batches(self, lat, rho):
        """Slices of the queries whose disks cross about _ROW_BUDGET grid rows in all."""
        r_lo, r_hi = self._row_range(lat, rho)
        return _batches(r_hi - r_lo + 1, _ROW_BUDGET)

    def spans(self, lat, lon, rho):
        """(query, start, stop) ranges of sorted points covering the disk of rho km round each
        query: per row it crosses, the cells spanning its width there, as a second run the part
        past the antimeridian. Each point within rho is in exactly one range."""
        cd, cols = self.cell_deg, self.cols
        r_lo, r_hi = self._row_range(lat, rho)
        owner, j = _expand(np.zeros(len(lat), dtype=np.int64), r_hi - r_lo + 1)
        row = r_lo[owner] + j
        half = self._half_width(lat, rho, owner, row)
        qlon = lon[owner]
        west, east = qlon - half, qlon + half
        c_lo, c_hi = gm.cell_cols(west, cd, cols), gm.cell_cols(east, cd, cols)
        base = row * cols
        lo, hi = base + c_lo, base + c_hi
        # rows the disk wraps round the antimeridian in: whole rows when the two ends meet round
        # the back (a cell must not be listed twice), else a second run on the far side
        wraps = np.flatnonzero((west < -180) | (east > 180) | (half >= 180))
        if len(wraps):
            w, e, b = west[wraps], east[wraps], base[wraps]
            far_lo = np.where(w < -180, gm.cell_cols(w + 360, cd, cols), 0)
            far_hi = np.where(w < -180, cols - 1, gm.cell_cols(e - 360, cd, cols))
            full = (half[wraps] >= 180) | np.where(w < -180, far_lo <= c_hi[wraps], far_hi >= c_lo[wraps])
            lo[wraps], hi[wraps] = (
                b + np.where(full, 0, c_lo[wraps]),
                b + np.where(full, cols - 1, c_hi[wraps]),
            )
            far = ~full
            owner = np.concatenate([owner, owner[wraps[far]]])
            lo = np.concatenate([lo, b[far] + far_lo[far]])
            hi = np.concatenate([hi, b[far] + far_hi[far]])
        start, stop = self._bounds(lo, hi)
        return owner, start, np.maximum(stop, start)

    def _bounds(self, lo, hi):
        """[start, stop) in the sorted points of the cells lo..hi (ids; lo > hi: none)."""
        if self.first is not None:
            return self.first[lo].astype(np.int64), self.first[np.maximum(hi + 1, lo)].astype(np.int64)
        return np.searchsorted(self.ids, lo, "left"), np.searchsorted(self.ids, hi, "right")

    def _half_width(self, lat, rho, owner, row):
        """Degrees of longitude either side of the query that its disk of rho km reaches within
        each grid row, slightly widened; 360 for the whole row."""
        delta = rho / MEAN_RADIUS_KM + _MARGIN_RAD
        phi = np.radians(lat)
        sin_p, cos_p, cos_d = np.sin(phi), np.cos(phi), np.cos(delta)
        # a disk is widest along the latitude where its edge runs north-south, and narrows away
        # from it, so within a row it is widest at that latitude clamped to the row
        with np.errstate(divide="ignore", invalid="ignore"):
            widest = np.where(cos_d > 0, sin_p / cos_d, 2.0)
        sin_y = np.clip(widest[owner], self.sin_edge[row], self.sin_edge[row + 1])
        cos_y = np.sqrt(np.maximum(1 - sin_y * sin_y, 0.0))
        ratio = _cos_half(cos_d[owner], sin_p[owner], cos_p[owner], sin_y, cos_y)
        half = np.degrees(np.arccos(np.clip(ratio, -1.0, 1.0))) + _MARGIN_DEG
        # disks of a quarter turn or more take whole rows: rare, and simplest to get right
        return np.where((ratio <= -1) | (delta[owner] >= math.pi / 2), 360.0, half)


def _cos_half(cos_d, sin_p, cos_p, sin_y, cos_y):
    """cos of the half-width in longitude of a disk (centre latitude p, angular radius d) along
    latitude y: -inf or below -1 when the whole parallel is inside, above 1 when none of it is."""
    num = cos_d - sin_p * sin_y
    den = cos_p * cos_y
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 1e-15, num / den, np.where(num <= 0, -np.inf, np.inf))


def _batches(sizes, budget):
    """(start, stop) slices of consecutive items whose sizes add up to about budget each (an
    item bigger than the budget gets a slice of its own)."""
    if not len(sizes):
        return []
    ends = np.cumsum(sizes)
    group = np.maximum(ends - 1, 0) // budget
    cuts = np.flatnonzero(np.diff(group)) + 1
    return list(zip([0, *cuts.tolist()], [*cuts.tolist(), len(sizes)], strict=True))


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = np.maximum(stop - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)
