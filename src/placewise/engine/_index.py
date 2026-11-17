"""Small helpers over the packs' public search APIs (placewise.packs.PointIndex and the polygon
layers' boundary queries)."""

import numpy as np

from placewise.packs import PointIndex


def best_per_query(q, value, n):
    """For pairs (q, value), the position of the smallest value per q: an (n,) array, -1 where q
    has no pair. Ties go to the earlier pair."""
    best = np.full(n, -1, dtype=np.int64)
    if len(q):
        order = np.lexsort((np.arange(len(q)), value, q))
        first = np.flatnonzero(np.diff(q[order], prepend=-1))
        best[q[order][first]] = order[first]
    return best


class RowIndex:
    """Nearest-neighbour search over chosen rows of a point layer."""

    def __init__(self, lat, lon, rows, cell_deg=None):
        """cell_deg None lets the index size its cells to the points' density."""
        self.rows = np.asarray(rows, dtype=np.int64)
        self.index = PointIndex(np.asarray(lat)[self.rows], np.asarray(lon)[self.rows], cell_deg)

    def nearest(self, lat, lon, k, max_km):
        """(rows (q, k), km (q, k)), nearest first; -1 and inf where fewer than k within max_km."""
        idx, dist = self.index.nearest(lat, lon, k=k, max_km=max_km)
        idx, dist = idx.reshape(len(lat), k), dist.reshape(len(lat), k)
        if not len(self.rows):
            return idx, dist  # all -1 and inf
        return np.where(idx >= 0, self.rows[np.maximum(idx, 0)], -1), dist
