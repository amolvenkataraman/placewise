"""Positions between fixes: great-circle interpolation, photo geotagging, camera clock offsets and
resampling to regular spacing.

A position is only interpolated between two fixes of the same segment that are at most
`max_gap_s` apart; anywhere else the answer is "unknown" rather than a straight line across a
gap the track never recorded. Track times must be non-decreasing.
"""

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from placewise.constants.track_ops import (
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

from ._steps import in_segment_steps, interpolate, require_sorted, segment_ids, step_km
from .track import Track

# Candidate offsets are scored in blocks of at most this many (offset, photo) pairs, to bound memory.
_SCORE_BLOCK = 2_000_000


class Geotags(NamedTuple):
    """Per-photo positions; `ok` is False (and the rest NaN) where the track can't say."""

    lat: np.ndarray
    lon: np.ndarray
    ok: np.ndarray
    fix_distance_m: np.ndarray  # metres from the position to the nearer bracketing fix
    fix_dt_s: np.ndarray  # seconds to the nearer bracketing fix


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


def _bracket(track, t, max_gap_s):
    """Left fix i, right fix j, fraction f and ok for each time in the flat array t."""
    time = track.time
    n = len(time)
    if n == 0:
        zeros = np.zeros(t.shape, dtype=np.int64)
        return zeros, zeros, np.zeros(t.shape), np.zeros(t.shape, dtype=bool)
    i = np.searchsorted(time, t, side="right") - 1
    ic = np.clip(i, 0, n - 1)
    j = np.minimum(ic + 1, n - 1)
    seg = segment_ids(track)
    exact = (i >= 0) & (time[ic] == t)
    span = time[j] - time[ic]
    inner = ~exact & (i >= 0) & (i < n - 1) & (seg[j] == seg[ic]) & (span <= max_gap_s)
    f = np.where(inner, (t - time[ic]) / np.where(inner, span, 1.0), 0.0)
    return ic, np.where(inner, j, ic), f, exact | inner


def _positions(track, t, max_gap_s):
    i, j, f, ok = _bracket(track, t, max_gap_s)
    lat, lon = interpolate(track, i, j, f)
    return np.where(ok, lat, np.nan), np.where(ok, lon, np.nan), ok, i, j


def _shaped(value, shape):
    value = np.asarray(value).reshape(shape)
    return value.item() if value.ndim == 0 else value


def _gap_limit(max_gap_s):
    return np.inf if max_gap_s is None else float(max_gap_s)


def position_at(track, times, max_gap_s=MAX_INTERP_GAP_S):
    """(lat, lon, ok) at each time (UTC unix seconds, scalar or array). Positions are great-circle
    interpolated between the fixes either side; a time exactly on a fix gets that fix. ok is False
    and lat / lon NaN outside the track, across a segment break or inside a gap longer than
    max_gap_s (None: any length)."""
    require_sorted(track)
    t = np.asarray(times, dtype=np.float64)
    lat, lon, ok, _, _ = _positions(track, t.reshape(-1), _gap_limit(max_gap_s))
    return _shaped(lat, t.shape), _shaped(lon, t.shape), _shaped(ok, t.shape)


def geotag(track, photo_times, max_gap_s=MAX_INTERP_GAP_S, clock_offset_s=0.0):
    """Positions for photos taken at `photo_times` (camera clock, unix seconds), after adding
    `clock_offset_s` (see estimate_clock_offset). Alongside each position, as a confidence: how far
    it is from the nearer of the two fixes it came from, in metres and seconds; 0 means the photo
    coincides with a real fix."""
    require_sorted(track)
    t = np.asarray(photo_times, dtype=np.float64) + clock_offset_s
    flat = t.reshape(-1)
    lat, lon, ok, i, j = _positions(track, flat, _gap_limit(max_gap_s))
    if len(track):
        d_i = np.asarray(haversine(lat, lon, track.lat[i], track.lon[i]))
        d_j = np.asarray(haversine(lat, lon, track.lat[j], track.lon[j]))
        dist = np.where(ok, np.minimum(d_i, d_j) * 1000, np.nan)
        dt = np.where(ok, np.minimum(flat - track.time[i], track.time[j] - flat), np.nan)
    else:
        dist = dt = np.full(flat.shape, np.nan)
    return Geotags(*(_shaped(v, t.shape) for v in (lat, lon, ok, dist, dt)))


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


def resample(track, every_s=None, every_m=None, max_gap_s=MAX_INTERP_GAP_S):
    """A new Track with fixes every `every_s` seconds or every `every_m` metres along the path,
    starting at each segment's first fix. Segments are resampled separately; grid points inside a
    gap longer than max_gap_s (None: any length) are dropped and the track resumes in a new
    segment after it. Optional columns are interpolated linearly (heading the short way round)."""
    if (every_s is None) == (every_m is None):
        raise ValueError("give exactly one of every_s or every_m")
    step = float(every_s if every_s is not None else every_m)
    if not step > 0:
        raise ValueError("the spacing must be positive")
    require_sorted(track)
    n = len(track)
    if n == 0:
        return track[:0]
    max_gap_s = _gap_limit(max_gap_s)
    time = track.time
    starts = np.asarray(track.segments)
    ends = np.r_[starts[1:], n] - 1
    if every_s is not None:
        axis = time
    else:
        legs = step_km(track) * 1000
        legs[~in_segment_steps(track)] = 0.0
        axis = np.r_[0.0, np.cumsum(legs)]
    # a regular grid per segment, built for all segments at once
    counts = np.floor((axis[ends] - axis[starts]) / step + 1e-9).astype(np.int64) + 1
    seg = np.repeat(np.arange(len(starts)), counts)
    k = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    target = axis[starts][seg] + k * step
    # the axis never decreases, so the bracketing fix is a search, kept inside the segment
    i = np.clip(np.searchsorted(axis, target, side="right") - 1, starts[seg], ends[seg])
    j = np.minimum(i + 1, ends[seg])
    span = axis[j] - axis[i]
    f = np.clip(np.where(span > 0, (target - axis[i]) / np.where(span > 0, span, 1.0), 0.0), 0.0, 1.0)
    ok = (f == 0) | (time[j] - time[i] <= max_gap_s)

    lat, lon = interpolate(track, i, j, f)
    # in time mode the grid itself is the time, free of rounding through the fraction
    columns = {"time": target if every_s is not None else time[i] + f * (time[j] - time[i])}
    columns |= {"lat": lat, "lon": lon}
    for name in track.columns[3:]:
        column = getattr(track, name)
        a, b = column[i], column[j]
        if name == "heading":
            columns[name] = (a + f * ((b - a + 180.0) % 360.0 - 180.0)) % 360.0
        else:
            columns[name] = a + f * (b - a)
    new_start = ok & ((k == 0) | ~np.r_[False, ok[:-1]])
    columns = {name: values[ok] for name, values in columns.items()}
    return Track.from_columns(columns, tuple(np.flatnonzero(new_start[ok])), track.meta)
