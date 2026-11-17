"""Discrete Fréchet distance between unit-vector sequences, exact, by a banded dynamic programme.

The classic DP c[i, j] = max(d(i, j), min(c[i-1, j], c[i, j-1], c[i-1, j-1])) is swept by
anti-diagonals i + j = k: every cell of one depends only on the two before it, so each is a single
numpy step. It runs on squared chord length, which orders pairs exactly as distance does and is
accurate at millimetres; the caller converts the answer to an angle.

Most of the n x m table can't matter. Any monotone walk through the table (a coupling) bounds the
answer from above by its largest cell, so with that bound U every cell whose value exceeds U is
dead: a coupling through it costs more than U. A cell's value only grows along a coupling, so the
live cells of each diagonal lie within the rows reachable from the live cells of the two before,
and the sweep only computes that band, trimmed to its outermost live cells. Dead cells inside the
band keep their (too large) values, which can never win a min against a live one, so the result
is bit-for-bit the full table's. For two recordings of one route the band is a few cells wide and
the cost is linear rather than quadratic; for unrelated tracks it widens to the full table.

The bound is the better of two couplings: by index (both walkers keep pace by fix count) and by
distance travelled (both keep pace by the share of their own path covered).
"""

import numpy as np

_CELLS = 1 << 20  # squared distances precomputed at once, which bounds temporary memory
_DIAGONALS = 64  # anti-diagonals per precomputed block, at most


def discrete_frechet_d2(pa, pb):
    """Squared chord length of the discrete Fréchet distance between unit vectors pa (n, 3) and pb (m, 3)."""
    n, m = len(pa), len(pb)
    a = [np.ascontiguousarray(pa[:, c]) for c in range(3)]
    # b reversed, so the cells of a diagonal (i up, j down) are contiguous in both
    b = [np.ascontiguousarray(pb[::-1, c]) for c in range(3)]
    bound = _coupling_bound(pa, pb)
    # buffers for diagonals k-1 and k-2, indexed by row + 1 (index 0 stands for row -1); every
    # slot outside the range last written is inf
    prev1, prev2 = np.full(n + 1, np.inf), np.full(n + 1, np.inf)
    written1 = written2 = (1, 1)  # [start, stop) slots holding values
    lo1, hi1, lo2, hi2 = 0, -1, n, -1  # live rows of diagonals k-1 and k-2 (empty: lo > hi)
    block, block_k, block_r = None, 0, 0
    for k in range(n + m - 1):
        if k == 0:
            lo, hi = 0, 0
        else:
            lo = max(min(lo1, lo2 + 1), k - m + 1)
            hi = min(max(hi1, hi2) + 1, k, n - 1)
        if lo > hi:  # no live cell anywhere: impossible with a true bound
            raise AssertionError("Fréchet band lost every live cell")
        if block is None or k - block_k >= len(block) or lo < block_r or hi >= block_r + block.shape[1]:
            block, block_k, block_r = _d2_block(a, b, n, m, k, lo, max(hi1, hi2, hi))
        d2 = block[k - block_k, lo - block_r : hi + 1 - block_r]
        if k:
            reach = np.minimum(np.minimum(prev1[lo : hi + 1], prev1[lo + 1 : hi + 2]), prev2[lo : hi + 1])
            d2 = np.maximum(d2, reach)
        # diagonal k-2 is no longer needed: reuse its buffer, clearing what this one doesn't cover
        start, stop = written2
        prev2[start : min(stop, lo + 1)] = np.inf
        prev2[max(start, hi + 2) : stop] = np.inf
        prev2[lo + 1 : hi + 2] = d2
        live = d2 <= bound
        first = int(live.argmax())
        if live[first]:
            lo_k, hi_k = lo + first, hi - int(live[::-1].argmax())
        else:
            lo_k, hi_k = n, -1
        prev1, prev2 = prev2, prev1
        written1, written2 = (lo + 1, hi + 2), written1
        lo1, hi1, lo2, hi2 = lo_k, hi_k, lo1, hi1
    return float(prev1[n])


def _d2_block(a, b, n, m, k, lo, hi):
    """Squared distances for a block of diagonals from k on, over rows lo.. wide enough for the
    band to grow by one row per diagonal: (diagonals, rows) with inf where no cell exists."""
    rows = max(1, min(hi - lo + 1 + _DIAGONALS, n - lo))
    count = max(1, min(_DIAGONALS, _CELLS // rows, n + m - 1 - k))
    r = np.arange(lo, lo + rows)
    kk = np.arange(k, k + count)[:, None]
    col = m - 1 - kk + r  # index into the reversed b of cell (r, kk - r)
    valid = (col >= 0) & (col < m)
    col = np.where(valid, col, 0)
    d2 = (a[0][r] - b[0][col]) ** 2 + (a[1][r] - b[1][col]) ** 2 + (a[2][r] - b[2][col]) ** 2
    return np.where(valid, d2, np.inf), k, lo


def _coupling_bound(pa, pb):
    """The smaller largest squared distance along two monotone walks from (0, 0) to (n-1, m-1),
    each cell computed exactly as the sweep computes it."""
    n, m = len(pa), len(pb)
    steps = max(n, m)
    t = np.arange(steps)
    by_index = ((t * (n - 1)) // max(steps - 1, 1), (t * (m - 1)) // max(steps - 1, 1))
    share_a, share_b = _shares(pa), _shares(pb)
    order = np.argsort(np.r_[share_a[1:], share_b[1:]], kind="stable")
    from_a = order < n - 1
    by_share = (np.r_[0, np.cumsum(from_a)], np.r_[0, np.cumsum(~from_a)])
    best = np.inf
    for i, j in (by_index, by_share):
        d2 = (pa[i, 0] - pb[j, 0]) ** 2 + (pa[i, 1] - pb[j, 1]) ** 2 + (pa[i, 2] - pb[j, 2]) ** 2
        best = min(best, float(d2.max()))
    return best


def _shares(p):
    """Share of the path's chord length covered at each point (by index when it has none)."""
    steps = np.linalg.norm(np.diff(p, axis=0), axis=1)
    total = float(steps.sum())
    if not total > 0:
        return np.linspace(0.0, 1.0, len(p))
    return np.r_[0.0, np.cumsum(steps)] / total
