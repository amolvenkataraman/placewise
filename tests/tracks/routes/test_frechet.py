"""The banded Fréchet sweep against the full table it replaces: results must be bit-for-bit equal.
Synthetic paths in open ocean near 0°N 20°W."""

import numpy as np
import pytest

from placewise.tracks._ops import unit_vectors
from placewise.tracks.routes._frechet import discrete_frechet_d2


def _full_table(pa, pb):
    """The unbanded anti-diagonal sweep: every cell of the n x m table."""
    n, m = len(pa), len(pb)
    ax, ay, az = (np.ascontiguousarray(pa[:, c]) for c in range(3))
    bx, by, bz = (np.ascontiguousarray(pb[::-1, c]) for c in range(3))
    prev1, prev2 = np.full(n + 1, np.inf), np.full(n + 1, np.inf)
    for k in range(n + m - 1):
        lo, hi = max(0, k - m + 1), min(k, n - 1)
        rows, cols = slice(lo, hi + 1), slice(m - 1 - k + lo, m - k + hi)
        d2 = (ax[rows] - bx[cols]) ** 2 + (ay[rows] - by[cols]) ** 2 + (az[rows] - bz[cols]) ** 2
        if k:
            reach = np.minimum(np.minimum(prev1[lo : hi + 1], prev1[lo + 1 : hi + 2]), prev2[lo : hi + 1])
            d2 = np.maximum(d2, reach)
        prev2[lo + 1 : hi + 2] = d2
        prev2[lo] = np.inf
        prev1, prev2 = prev2, prev1
    return float(prev1[n])


def _walk(rng, n, start=(0.0, -20.0), step=3e-4):
    pts = np.array(start) + np.cumsum(rng.normal(0, step, size=(n, 2)), axis=0)
    return unit_vectors(pts[:, 0], pts[:, 1])


def _noisy_copy(rng, p_latlon, noise):
    lat, lon = p_latlon
    return unit_vectors(lat + rng.normal(0, noise, len(lat)), lon + rng.normal(0, noise, len(lon)))


@pytest.mark.parametrize("seed", range(40))
def test_band_matches_the_full_table_on_random_pairs(seed):
    rng = np.random.default_rng(seed)
    n, m = rng.integers(1, 120, size=2)
    kind = seed % 4
    if kind == 0:  # unrelated walks
        pa, pb = _walk(rng, n), _walk(rng, m)
    else:  # two noisy recordings of one path, resampled differently
        base = np.array([0.0, -20.0]) + np.cumsum(rng.normal(0, 3e-4, size=(200, 2)), axis=0)
        ia = np.sort(rng.choice(200, size=min(n, 200), replace=False))
        ib = np.sort(rng.choice(200, size=min(m, 200), replace=False))
        if kind == 3:
            ib = ib[::-1]  # the other way round
        noise = [1e-6, 1e-5, 1e-4][kind - 1]
        pa = _noisy_copy(rng, (base[ia, 0], base[ia, 1]), noise)
        pb = _noisy_copy(rng, (base[ib, 0], base[ib, 1]), noise)
    assert discrete_frechet_d2(pa, pb) == _full_table(pa, pb)
    assert discrete_frechet_d2(pb, pa) == _full_table(pb, pa)


def test_band_matches_on_long_similar_tracks():
    rng = np.random.default_rng(7)
    base = np.array([0.0, -20.0]) + np.cumsum(rng.normal(0, 2e-4, size=(1500, 2)), axis=0)
    pa = _noisy_copy(rng, (base[:, 0], base[:, 1]), 2e-5)
    pb = _noisy_copy(rng, (base[::2, 0], base[::2, 1]), 2e-5)
    assert discrete_frechet_d2(pa, pb) == _full_table(pa, pb)


def test_degenerate_inputs():
    one = unit_vectors(np.array([0.0]), np.array([-20.0]))
    same = unit_vectors(np.zeros(5), np.full(5, -20.0))  # one place, five fixes
    line = unit_vectors(np.zeros(7), np.linspace(-20.0, -19.9, 7))
    for pa, pb in [(one, one), (one, line), (line, one), (same, line), (line, same), (same, same)]:
        assert discrete_frechet_d2(pa, pb) == _full_table(pa, pb)
