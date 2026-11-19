"""The settlement cells of a GHS-SMOD grid, and the clusters they form.

Cells are kept as parallel arrays sorted by (row, col): only the few classes asked for (about
1.1 million of the 650 million cells of the 2020 world grid), so the grid itself is never held
whole. Clusters are the 4-connected groups of cells with the same key (class and country), as
runs of cells along a row, which is also what the outline tracer reads.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class Cells:
    """Cells sorted by (row, col); `group` is the class group of each (an index)."""

    row: np.ndarray
    col: np.ndarray
    group: np.ndarray
    width: int  # of the grid: row * width + col is a cell's linear index

    @property
    def index(self):
        return self.row.astype(np.int64) * self.width + self.col

    def subset(self, keep):
        return Cells(self.row[keep], self.col[keep], self.group[keep], self.width)

    def find(self, row, col):
        """Position of each (row, col) among the cells, -1 where it is not one."""
        index = self.index
        want = np.asarray(row, dtype=np.int64) * self.width + np.asarray(col, dtype=np.int64)
        at = np.searchsorted(index, want)
        ok = at < len(index)
        ok[ok] = index[at[ok]] == want[ok]
        return np.where(ok, at, -1)


def read_cells(tif, groups):
    """The cells of a GeoTiff whose value is a key of `groups` ({value: group index})."""
    values = np.array(sorted(groups))
    lut = np.full(int(values.max()) + 1, -1, dtype=np.int8)
    lut[values] = [groups[v] for v in values.tolist()]
    rows, cols, kinds = [], [], []
    for top, band in tif.row_bands():
        r, c = np.nonzero(np.isin(band, values))
        rows.append((r + top).astype(np.int32))
        cols.append(c.astype(np.int32))
        kinds.append(lut[band[r, c]])
    return Cells(np.concatenate(rows), np.concatenate(cols), np.concatenate(kinds), tif.width)


@dataclass
class Clusters:
    """Runs of cells and the cluster of each: run k is row[k], cols [c0[k], c1[k]), key[k]."""

    row: np.ndarray
    c0: np.ndarray
    c1: np.ndarray
    key: np.ndarray
    label: np.ndarray  # cluster of each run, 0..count-1 in order of first run
    run_of_cell: np.ndarray  # the run of each cell
    count: int

    def runs(self, cluster):
        """[(row, c0, c1), ...] of one cluster (use `members` for many)."""
        k = np.flatnonzero(self.label == cluster)
        return list(zip(self.row[k].tolist(), self.c0[k].tolist(), self.c1[k].tolist(), strict=True))

    def members(self):
        """For each cluster, the indexes of its runs (one argsort, not a scan per cluster)."""
        order = np.argsort(self.label, kind="stable")
        bounds = np.searchsorted(self.label[order], np.arange(self.count + 1))
        return [order[bounds[i] : bounds[i + 1]] for i in range(self.count)]


def clusters(cells, key):
    """The 4-connected clusters of cells with equal `key` (an int per cell)."""
    key = np.asarray(key, dtype=np.int64)
    n = len(key)
    if not n:
        empty = np.zeros(0, dtype=np.int64)
        return Clusters(empty, empty, empty, empty, empty, empty, 0)
    index = cells.index
    # a run starts where the row changes, the columns skip, or the key changes
    new = np.ones(n, dtype=bool)
    new[1:] = (index[1:] != index[:-1] + 1) | (cells.row[1:] != cells.row[:-1]) | (key[1:] != key[:-1])
    run_of_cell = np.cumsum(new) - 1
    starts = np.flatnonzero(new)
    ends = np.append(starts[1:], n)
    row, c0 = cells.row[starts].astype(np.int64), cells.col[starts].astype(np.int64)
    c1 = cells.col[ends - 1].astype(np.int64) + 1
    # runs joined through a cell and the one below it with the same key
    below = cells.find(cells.row.astype(np.int64) + 1, cells.col)
    hit = np.flatnonzero(below >= 0)
    hit = hit[key[below[hit]] == key[hit]]
    pairs = np.unique(np.stack([run_of_cell[hit], run_of_cell[below[hit]]], axis=1), axis=0)
    label = _components(len(starts), pairs)
    return Clusters(row, c0, c1, key[starts], label, run_of_cell, int(label.max()) + 1)


def _components(n, pairs):
    """Connected components of n nodes joined by `pairs`, numbered in order of first node."""
    parent = list(range(n))

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in pairs.tolist():
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([root(a) for a in range(n)], dtype=np.int64)
    _, label = np.unique(roots, return_inverse=True)  # roots are each component's first node
    return label.ravel()
