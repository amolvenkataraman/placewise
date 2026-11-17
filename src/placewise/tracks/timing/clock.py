"""Camera clock offsets: how far a camera's clock is from the track's (UTC) time, estimated from
photos with their own GPS when there are some, else from when the track was recording.
"""

from dataclasses import dataclass

import numpy as np

from placewise.constants.tracks import (
    CLOCK_COARSE_STEP_S,
    CLOCK_FINE_STEP_S,
    CLOCK_GOOD_RESIDUAL_M,
    CLOCK_NEAR_FIX_S,
    CLOCK_SEARCH_S,
    MAX_INTERP_GAP_S,
    STAY_MAX_BRIDGE_S,
    STAY_RADIUS_M,
)
from placewise.geo.distances import haversine
from placewise.model._base import Model

from .._ops import require_sorted
from .positions import _bracket, _gap_limit, _positions

# Candidate offsets are scored in blocks of at most this many (offset, photo) pairs, to bound memory.
_SCORE_BLOCK = 2_000_000


@dataclass(frozen=True, slots=True)
class ClockOffset(Model):
    """Seconds to add to camera timestamps to get track (UTC) time.

    method "gps": matched against photos that carry their own position; `residual_m` is the
    median distance between their GPS and the track there, `quality` the share within
    CLOCK_GOOD_RESIDUAL_M. method "coverage": no photo GPS, so the offset that puts the most
    photos where the track was recording; `quality` is that share times how sharply the offset
    stands out (0 when every candidate fits equally well)."""

    offset_s: float
    quality: float
    method: str
    n_photos: int
    residual_m: float | None = None


def estimate_clock_offset(
    track,
    photo_times,
    photo_lats=None,
    photo_lons=None,
    search_s=CLOCK_SEARCH_S,
    max_gap_s=MAX_INTERP_GAP_S,
):
    """Estimate a camera's clock offset against the track, returning a ClockOffset.

    With photos that carry GPS (pass photo_lats / photo_lons, NaN where a photo has none), the
    offset minimises the median distance between those photos' GPS and the track position at
    their corrected times; photos the track can't place count as infinitely far, so the median
    needs over half of them on the track. Without GPS, it maximises the number of photos that
    land where the track was recording, near a fix, or inside a quiet stretch where the phone
    didn't move (a stop), and takes the centre of the range of offsets that do so. Offsets are
    scanned every CLOCK_COARSE_STEP_S over `search_s`, then refined to CLOCK_FINE_STEP_S; ties
    go to the offset nearest zero."""
    require_sorted(track)
    times = np.asarray(photo_times, dtype=np.float64).reshape(-1)
    lo, hi = float(search_s[0]), float(search_s[1])
    if hi < lo:
        raise ValueError("search_s must be (earliest, latest)")
    max_gap_s = _gap_limit(max_gap_s)
    has_gps = np.zeros(len(times), dtype=bool)
    if photo_lats is not None and photo_lons is not None:
        plat = np.asarray(photo_lats, dtype=np.float64).reshape(-1)
        plon = np.asarray(photo_lons, dtype=np.float64).reshape(-1)
        if len(plat) != len(times) or len(plon) != len(times):
            raise ValueError("photo_lats and photo_lons need one value per photo (NaN for none)")
        has_gps = np.isfinite(plat) & np.isfinite(plon)
    if not len(times) or not len(track):
        return ClockOffset(0.0, 0.0, "gps" if has_gps.any() else "coverage", 0)
    if has_gps.any():
        return _offset_from_gps(track, times[has_gps], plat[has_gps], plon[has_gps], lo, hi, max_gap_s)
    return _offset_from_coverage(track, times, lo, hi, max_gap_s)


def _grid(lo, hi, step):
    return lo + np.arange(int(np.floor((hi - lo) / step + 1e-9)) + 1) * step


def _scored(offsets, times, score):
    """score(corrected times, shape (offsets, photos)) -> one value per offset, in blocks."""
    rows = max(1, _SCORE_BLOCK // len(times))
    return np.concatenate(
        [score(offsets[s : s + rows, None] + times[None, :]) for s in range(0, len(offsets), rows)]
    )


def _best(offsets, values):
    """Index of the smallest value; ties go to the offset nearest zero."""
    return int(np.lexsort((np.abs(offsets), values))[0])


def _offset_from_gps(track, times, plat, plon, lo, hi, max_gap_s):
    def residuals(t):
        lat, lon, ok, _, _ = _positions(track, t.reshape(-1), max_gap_s)
        rows = t.shape[0]
        d = np.asarray(haversine(lat, lon, np.tile(plat, rows), np.tile(plon, rows))) * 1000
        return np.where(ok, d, np.inf).reshape(t.shape)

    def median(t):
        return np.median(residuals(t), axis=1)

    coarse = _grid(lo, hi, CLOCK_COARSE_STEP_S)
    best = coarse[_best(coarse, _scored(coarse, times, median))]
    fine = _grid(max(lo, best - CLOCK_COARSE_STEP_S), min(hi, best + CLOCK_COARSE_STEP_S), CLOCK_FINE_STEP_S)
    offset = float(fine[_best(fine, _scored(fine, times, median))])
    at_best = residuals((times + offset)[None, :])[0]
    residual = float(np.median(at_best))
    quality = float(np.mean(at_best <= CLOCK_GOOD_RESIDUAL_M))
    return ClockOffset(offset, quality, "gps", len(times), residual if np.isfinite(residual) else None)


def _supported(track, t, max_gap_s):
    """Which photos at times t (any shape) fall where the track was recording, near a fix, or in a
    quiet stretch between two fixes in the same place."""
    flat = t.reshape(-1)
    time, n = track.time, len(track)
    ok = _bracket(track, flat, max_gap_s)[3]
    k = np.searchsorted(time, flat)
    i, j = np.clip(k - 1, 0, n - 1), np.clip(k, 0, n - 1)
    near = np.minimum(np.abs(flat - time[i]), np.abs(time[j] - flat)) <= CLOCK_NEAR_FIX_S
    still = (k > 0) & (k < n) & (time[j] - time[i] <= STAY_MAX_BRIDGE_S)
    if still.any():
        idx = np.flatnonzero(still)
        a, b = i[idx], j[idx]
        moved_km = np.asarray(haversine(track.lat[a], track.lon[a], track.lat[b], track.lon[b]))
        still[idx] = moved_km * 1000 <= STAY_RADIUS_M
    return (ok | near | still).reshape(t.shape)


def _offset_from_coverage(track, times, lo, hi, max_gap_s):
    def count(t):
        return _supported(track, t, max_gap_s).sum(axis=1)

    coarse = _grid(lo, hi, CLOCK_COARSE_STEP_S)
    counts = _scored(coarse, times, count)
    top = counts.max()
    if top == 0:
        return ClockOffset(0.0, 0.0, "coverage", len(times))
    # every offset on a plateau fits the photos equally well; its centre is the best guess
    hit = counts == top
    edges = np.flatnonzero(np.diff(np.r_[False, hit, False].astype(np.int8)))
    runs = list(zip(edges[::2], edges[1::2] - 1, strict=True))
    first, last = max(runs, key=lambda r: (r[1] - r[0], -abs(coarse[r[0]] + coarse[r[1]])))
    left = _plateau_edge(coarse[first], -1, lo, top, times, count)
    right = _plateau_edge(coarse[last], +1, hi, top, times, count)
    sharpness = 1.0 - hit.sum() / len(coarse)
    return ClockOffset((left + right) / 2, float(top / len(times) * sharpness), "coverage", len(times))


def _plateau_edge(offset, direction, limit, top, times, count):
    """How far the plateau ending at `offset` extends in `direction`, to CLOCK_FINE_STEP_S."""
    reach = min(CLOCK_COARSE_STEP_S, abs(limit - offset))
    fine = offset + direction * _grid(0.0, reach, CLOCK_FINE_STEP_S)
    off = np.flatnonzero(_scored(fine, times, count) != top)
    return float(fine[off[0] - 1] if len(off) else fine[-1])
