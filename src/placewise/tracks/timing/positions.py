"""Positions between fixes: great-circle interpolation, photo geotagging and resampling to regular
spacing.

A position is only interpolated between two fixes of the same segment that are at most
`max_gap_s` apart; anywhere else the answer is "unknown" rather than a straight line across a
gap the track never recorded. Track times must be non-decreasing.
"""

from typing import NamedTuple

import numpy as np

from placewise.constants.tracks import MAX_INTERP_GAP_S
from placewise.geo.distances import haversine

from .._ops import in_segment_steps, interpolate, require_sorted, segment_ids, step_km
from ..track import Track


class Geotags(NamedTuple):
    """Per-photo positions; `ok` is False (and the rest NaN) where the track can't say."""

    lat: np.ndarray
    lon: np.ndarray
    ok: np.ndarray
    fix_distance_m: np.ndarray  # metres from the position to the nearer bracketing fix
    fix_dt_s: np.ndarray  # seconds to the nearer bracketing fix


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
