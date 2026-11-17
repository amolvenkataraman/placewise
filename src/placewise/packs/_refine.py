"""A finer, in-memory grid per polygon feature, built on first use.

The pack's grid answers a cell outright only when one feature wholly covers it, so near borders
every point needs the exact even-odd test, whose cost grows with the number of edges its ray meets
(dozens on a ragged coastline). Here each feature's edges are rasterised onto cells of about
REFINE_CELL_DEG:

- a point in a fine cell no edge touches shares that cell's answer, found once from its centre;
- a point in a touched cell takes the answer at the cell's south-east corner (found once, by the
  full test) and flips it for every edge crossed on the way there: east to the cell's edge, then
  south along it. Only the few edges in the cell can be crossed.

Both give the full test's answer. Where an edge passes within a hair of the path's corner or ends,
the point gets the full test instead. The answer for a point exactly on an edge may still differ,
as it may anywhere.
"""

import math

import numpy as np

from placewise.constants.packs import REFINE_CELL_DEG

from . import _geometry as gm

# degrees: crossings nearer than this to a path's corner or ends send the point to the full test;
# far above float64 rounding at 180 degrees, far below the 1e-7 degree storage grid
_TOL = 1e-9
_PAIR_BUDGET = 4_000_000


class Refinement:
    def __init__(self, edges, cell_deg):
        self.edges = tuple(np.asarray(e, dtype=np.float64) for e in edges)  # ya, xa, yb, xb
        self.cell_deg = cell_deg / max(1, math.ceil(round(cell_deg / REFINE_CELL_DEG, 9)))
        self.rows, self.cols = gm.grid_shape(self.cell_deg)
        pair_cell, pair_edge = gm.edge_cell_pairs(*self.edges, self.cell_deg, self.rows, self.cols)
        order = np.argsort(pair_cell, kind="stable")
        self.pair_cell, self.pair_edge = pair_cell[order], pair_edge[order]
        self.touched = self.pair_cell[np.flatnonzero(np.diff(self.pair_cell, prepend=-1))]
        # answers found so far: runs of untouched cells (at a centre), touched cells (at the corner)
        self.runs = _Memo()
        self.corners = _Memo()

    def contains(self, lat, lon):
        ids = gm.cell_rows(lat, self.cell_deg, self.rows) * self.cols + gm.cell_cols(
            lon, self.cell_deg, self.cols
        )
        touched = _member(ids, self.touched)
        inside = np.empty(len(lat), dtype=bool)
        free = ~touched
        if free.any():
            # along a row, untouched cells between the same two touched ones form a run no edge
            # crosses, so one centre answers for the whole run
            cells = ids[free]
            run = (cells // self.cols) * (len(self.touched) + 1) + np.searchsorted(self.touched, cells)
            runs, first, inverse = np.unique(run, return_index=True, return_inverse=True)
            inside[free] = self.runs.get(runs, cells[first], self._centre_inside)[inverse.ravel()]
        if touched.any():
            idx = np.flatnonzero(touched)
            inside[idx] = self._local(lat[idx], lon[idx], ids[idx])
        return inside

    def _centre_inside(self, cells):
        # no edge touches these cells, so each centre speaks for its whole cell
        lat = -90.0 + (cells // self.cols + 0.5) * self.cell_deg
        lon = -180.0 + (cells % self.cols + 0.5) * self.cell_deg
        return gm.even_odd_rows(lat, lon, *self.edges)

    def _corner_inside(self, cells):
        lat = -90.0 + (cells // self.cols) * self.cell_deg
        lon = -180.0 + (cells % self.cols + 1) * self.cell_deg
        return gm.even_odd_rows(lat, lon, *self.edges)

    def _local(self, lat, lon, ids):
        """Even-odd for points in touched cells, from each cell's south-east corner."""
        cells, inverse = np.unique(ids, return_inverse=True)
        parity = self.corners.get(cells, cells, self._corner_inside)[inverse.ravel()].astype(np.int64)
        start = np.searchsorted(self.pair_cell, ids, "left")
        stop = np.searchsorted(self.pair_cell, ids, "right")
        # the same expressions as the corners above, so the path ends exactly there
        x_e = -180.0 + (ids % self.cols + 1) * self.cell_deg
        y_s = -90.0 + (ids // self.cols) * self.cell_deg
        unsure = np.zeros(len(lat), dtype=bool)
        cum = np.cumsum(stop - start)
        cuts = np.searchsorted(cum, np.arange(_PAIR_BUDGET, cum[-1], _PAIR_BUDGET), "left")
        for c0, c1 in zip([0, *cuts], [*cuts, len(lat)], strict=True):
            point, k = _expand(start[c0:c1], stop[c0:c1])
            e = self.pair_edge[k]
            ya, xa, yb, xb = (a[e] for a in self.edges)
            point += c0
            plat, plon, pxe, pys = lat[point], lon[point], x_e[point], y_s[point]
            with np.errstate(invalid="ignore", divide="ignore"):
                # east from the point to the cell's edge: the full test's crossing rule and arithmetic
                across = (ya > plat) != (yb > plat)
                x_cross = xa + (plat - ya) * (xb - xa) / (yb - ya)
                east = across & (plon < x_cross) & (x_cross <= pxe)
                # then south along that edge to the corner; a vertex on the line counts as west of
                # it, matching the full test's view from the corner
                down = (xa > pxe) != (xb > pxe)
                y_cross = ya + (pxe - xa) * (yb - ya) / (xb - xa)
                south = down & (pys <= y_cross) & (y_cross < plat)
                near = (across & (np.abs(x_cross - pxe) <= _TOL)) | (
                    down & ((np.abs(y_cross - plat) <= _TOL) | (np.abs(y_cross - pys) <= _TOL))
                )
            n = c1 - c0
            parity[c0:c1] += np.bincount(point[east ^ south] - c0, minlength=n)
            unsure[c0:c1] |= np.bincount(point[near] - c0, minlength=n) > 0
        inside = (parity & 1).astype(bool)
        if unsure.any():
            inside[unsure] = gm.even_odd(lat[unsure], lon[unsure], *self.edges)
        return inside


class _Memo:
    """A boolean per integer key, computed on first request."""

    def __init__(self):
        self.ids = np.zeros(0, dtype=np.int64)
        self.values = np.zeros(0, dtype=bool)

    def get(self, keys, cells, compute):
        """Values for unique keys; compute(cells[i]) gives the value for a key not seen before."""
        found = _member(keys, self.ids)
        result = np.empty(len(keys), dtype=bool)
        if found.any():
            result[found] = self.values[np.searchsorted(self.ids, keys[found])]
        if not found.all():
            new = keys[~found]
            result[~found] = values = compute(cells[~found])
            ids = np.concatenate([self.ids, new])
            order = np.argsort(ids, kind="stable")
            self.ids, self.values = ids[order], np.concatenate([self.values, values])[order]
        return result


def _member(values, sorted_set):
    """Which values occur in a sorted array."""
    if not len(sorted_set):
        return np.zeros(len(values), dtype=bool)
    pos = np.minimum(np.searchsorted(sorted_set, values), len(sorted_set) - 1)
    return sorted_set[pos] == values


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = stop - start
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)
