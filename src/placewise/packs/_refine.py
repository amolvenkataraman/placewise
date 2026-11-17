"""Finer, in-memory grids for the features of a polygon layer that are asked about often.

The pack's grid answers a cell outright only when one feature wholly covers it, so near borders
every point needs the exact even-odd test, whose cost grows with the number of edges its ray meets
(dozens on a ragged coastline). Here each such feature's edges are rasterised onto cells of about
REFINE_CELL_DEG:

- a point in a fine cell none of its feature's edges touch shares the answer of that cell's run
  (the untouched cells between two touched ones along a row), found once from a centre;
- a point in a touched cell takes the answer at the cell's south-east corner (found once, by the
  full test) and flips it for every edge crossed on the way there: east to the cell's edge, then
  south along it. Only the feature's few edges in the cell can be crossed.

Both give the full test's answer. Where an edge passes within a hair of the path's corner or ends,
the point gets the full test instead. The answer for a point exactly on an edge may still differ,
as it may anywhere.

The grids of all refined features live in one set of arrays keyed by (feature, cell), so a batch
of (point, feature) pairs, whatever the features, is answered in a few array operations; features
are added in batches as they become worth it.
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
    """Fine grids for chosen features of a layer, whose edges are ya[offsets[f]:offsets[f + 1]]
    (and likewise xa, yb, xb). len() is the number of features refined so far."""

    def __init__(self, offsets, edges, cell_deg, full):
        """full(lat, lon, feature): the exact even-odd test of a few points against their features
        (cell centres and corners, many at once, use the sort-based gm.even_odd_pairs)."""
        self._full = full
        self.offsets = np.asarray(offsets, dtype=np.int64)
        self.edges = tuple(np.asarray(e, dtype=np.float64) for e in edges)  # ya, xa, yb, xb
        self.cell_deg = cell_deg / max(1, math.ceil(round(cell_deg / REFINE_CELL_DEG, 9)))
        self.rows, self.cols = gm.grid_shape(self.cell_deg)
        self.n_cells = self.rows * self.cols
        self.refined = np.zeros(len(self.offsets) - 1, dtype=bool)
        # every (cell, edge) touch of the refined features as key = feature * n_cells + cell,
        # sorted, with its edge; and the distinct keys (the touched cells)
        self.pair_key = np.zeros(0, dtype=np.int64)
        self.pair_edge = np.zeros(0, dtype=np.int64)
        self.touched = np.zeros(0, dtype=np.int64)
        # answers found so far: runs of untouched cells (at a centre), touched cells (at the corner)
        self.runs = _Memo()
        self.corners = _Memo()

    def __len__(self):
        return int(self.refined.sum())

    def add(self, features):
        """Build the fine grids of these features (those not built yet)."""
        new = np.unique(np.asarray(features, dtype=np.int64))
        new = new[~self.refined[new]]
        if not len(new):
            return
        owner, edge = gm._expand(self.offsets[new], self.offsets[new + 1])
        ya, xa, yb, xb = (a[edge] for a in self.edges)
        cell, which = gm.edge_cell_pairs(ya, xa, yb, xb, self.cell_deg, self.rows, self.cols)
        key = np.concatenate([self.pair_key, new[owner[which]] * self.n_cells + cell])
        edge = np.concatenate([self.pair_edge, edge[which]])
        order = np.argsort(key, kind="stable")
        self.pair_key, self.pair_edge = key[order], edge[order]
        self.touched = self.pair_key[np.flatnonzero(np.diff(self.pair_key, prepend=-1))]
        self.refined[new] = True

    def contains(self, lat, lon, feature):
        """Even-odd containment of each point in its own (refined) feature."""
        cols = self.cols
        cell = gm.cell_rows(lat, self.cell_deg, self.rows) * cols + gm.cell_cols(lon, self.cell_deg, cols)
        key = feature * self.n_cells + cell
        pos = np.searchsorted(self.touched, key)
        nxt = self.touched[np.minimum(pos, len(self.touched) - 1)] if len(self.touched) else key + 1
        touched = nxt == key
        inside = np.empty(len(lat), dtype=bool)
        free = np.flatnonzero(~touched)
        if len(free):
            # along a row, a feature's untouched cells between the same two touched ones form a
            # run none of its edges cross, so one centre answers for the whole run
            f, row, nx = feature[free], cell[free] // cols, nxt[free]
            same_row = (
                (pos[free] < len(self.touched))
                & (nx // self.n_cells == f)
                & ((nx % self.n_cells) // cols == row)
            )
            run = (f * self.rows + row) * (cols + 1) + np.where(same_row, nx % cols, cols)
            runs, first, inverse = np.unique(run, return_index=True, return_inverse=True)
            rep = free[first]
            inside[free] = self.runs.get(
                runs, lambda miss: self._centre_inside(cell[rep[miss]], feature[rep[miss]])
            )[inverse.ravel()]
        hit = np.flatnonzero(touched)
        if len(hit):
            inside[hit] = self._local(lat[hit], lon[hit], cell[hit], feature[hit], key[hit])
        return inside

    def _centre_inside(self, cells, feature):
        # none of the feature's edges touch these cells, so each centre speaks for its whole cell
        lat = -90.0 + (cells // self.cols + 0.5) * self.cell_deg
        lon = -180.0 + (cells % self.cols + 0.5) * self.cell_deg
        return gm.even_odd_pairs(lat, lon, feature, self.offsets, *self.edges)

    def _corner_inside(self, cells, feature):
        lat = -90.0 + (cells // self.cols) * self.cell_deg
        lon = -180.0 + (cells % self.cols + 1) * self.cell_deg
        return gm.even_odd_pairs(lat, lon, feature, self.offsets, *self.edges)

    def _local(self, lat, lon, ids, feature, keys):
        """Even-odd for points in cells their feature's edges touch, from each cell's south-east
        corner."""
        cells, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
        parity = self.corners.get(
            cells, lambda miss: self._corner_inside(ids[first[miss]], feature[first[miss]])
        )
        parity = parity[inverse.ravel()].astype(np.int64)
        start = np.searchsorted(self.pair_key, keys, "left")
        stop = np.searchsorted(self.pair_key, keys, "right")
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
            inside[unsure] = self._full(lat[unsure], lon[unsure], feature[unsure])
        return inside


class _Memo:
    """A boolean per integer key, computed on first request."""

    def __init__(self):
        self.ids = np.zeros(0, dtype=np.int64)
        self.values = np.zeros(0, dtype=bool)

    def get(self, keys, compute):
        """Values for sorted unique keys; compute(positions) gives those of keys[positions], the
        keys not seen before."""
        found = _member(keys, self.ids)
        result = np.empty(len(keys), dtype=bool)
        if found.any():
            result[found] = self.values[np.searchsorted(self.ids, keys[found])]
        if not found.all():
            missing = np.flatnonzero(~found)
            new = keys[missing]
            result[missing] = values = compute(missing)
            at = np.searchsorted(self.ids, new)  # new keys are sorted, so they go in in order
            self.ids, self.values = np.insert(self.ids, at, new), np.insert(self.values, at, values)
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
