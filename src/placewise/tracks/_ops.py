"""Helpers shared by the track operations: segment bookkeeping, legs between consecutive fixes,
rolling windows, great-circle interpolation along legs and locating a boundary within a leg."""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from placewise.constants.distance import METRES_PER
from placewise.constants.tracks import BOUNDARY_BISECTIONS
from placewise.geo.bearing import along
from placewise.geo.distances import haversine

from .track import Track

M_PER_KM = METRES_PER["km"]


def columns(track):
    return {name: getattr(track, name) for name in track.columns}


def replace(track, **changed):
    """A new Track with some columns swapped, same segments and meta."""
    return Track.from_columns({**columns(track), **changed}, track.segments or None, track.meta)


def bounds(track):
    """(start, end) index pairs of each segment, end exclusive."""
    starts = list(track.segments)
    return list(zip(starts, [*starts[1:], len(track)][: len(starts)], strict=True))


def leg_metres(lat, lon):
    return np.asarray(haversine(lat[:-1], lon[:-1], lat[1:], lon[1:])) * M_PER_KM


def speed(metres, seconds):
    """Metres / seconds, with a zero-time hop counting as infinitely fast unless it went nowhere."""
    with np.errstate(divide="ignore", invalid="ignore"):
        v = metres / seconds
    return np.where(seconds > 0, v, np.where(metres > 0, np.inf, 0.0))


def windows(values, groups, size):
    """(n, size) centred windows of `values`, NaN where the window runs off the array or into
    another group (segment), so filters never mix recordings."""
    half = size // 2
    pad_v = np.pad(np.asarray(values, dtype=np.float64), half, constant_values=np.nan)
    pad_g = np.pad(np.asarray(groups), half, constant_values=-1)
    v = sliding_window_view(pad_v, 2 * half + 1)
    g = sliding_window_view(pad_g, 2 * half + 1)
    return np.where(g == np.asarray(groups)[:, None], v, np.nan)


def nanmedian_rows(w):
    """Median of each row ignoring NaN (NaN for an all-NaN row). Sorting puts NaN last, so the
    median sits at the middle of each row's valid prefix; much faster than np.nanmedian."""
    s = np.sort(w, axis=1)
    count = np.sum(~np.isnan(w), axis=1)
    rows = np.arange(len(w))
    lo, hi = np.maximum((count - 1) // 2, 0), np.maximum(count // 2, 0)
    med = (s[rows, lo] + s[rows, hi]) / 2
    med[count == 0] = np.nan
    return med


def point_weights(track, legs_within=None):
    """Seconds each sample stands for: half of each adjacent within-segment leg, so time-weighted
    means are right under irregular ("smart") recording and ignore gaps between segments."""
    n = len(track)
    w = np.zeros(n)
    if n < 2:
        return w
    mask = in_segment_steps(track) if legs_within is None else legs_within
    half = np.where(mask, np.diff(track.time), 0.0) / 2
    w[:-1] += half
    w[1:] += half
    return w


def require_sorted(track):
    t = track.time
    if len(t) > 1 and not np.all(t[1:] >= t[:-1]):
        raise ValueError("track times must be non-decreasing; sort the track first")


def segment_ids(track):
    """Segment number of every point."""
    n = len(track)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    bounds = np.asarray((*track.segments, n))
    return np.repeat(np.arange(len(track.segments)), np.diff(bounds))


def in_segment_steps(track):
    """For each step k (fix k -> k + 1), whether both fixes belong to the same recording."""
    seg = segment_ids(track)
    return seg[1:] == seg[:-1]


def step_km(track):
    """Great-circle length of every step, segment breaks included."""
    lat, lon = track.lat, track.lon
    return np.asarray(haversine(lat[:-1], lon[:-1], lat[1:], lon[1:]), dtype=np.float64).reshape(-1)


def interpolate(track, i, j, f):
    """(lat, lon) a fraction f of the way from fix i to fix j along the great circle; fixes
    themselves are returned untouched so exact hits don't pick up round-trip error."""
    lat, lon = track.lat, track.lon
    i, j, f = np.asarray(i), np.asarray(j), np.asarray(f, dtype=np.float64)
    if i.size == 0 or len(lat) == 0:  # nothing to place; callers mask these as not ok
        return np.zeros(i.shape), np.zeros(i.shape)
    ilat, ilon = along(lat[i], lon[i], lat[j], lon[j], f)
    at_fix = (i == j) | (f == 0)
    return np.where(at_fix, lat[i], ilat), np.where(at_fix, lon[i], ilon)


def bisect_change(lat1, lon1, lat2, lon2, same):
    """Fraction along each great-circle step at which `same(lat, lon)` (True at the start, False
    at the end) first turns False, for many steps at once."""
    lo = np.zeros(len(lat1))
    hi = np.ones(len(lat1))
    for _ in range(BOUNDARY_BISECTIONS):
        mid = (lo + hi) / 2
        mlat, mlon = along(lat1, lon1, lat2, lon2, mid)
        still = np.asarray(same(np.atleast_1d(mlat), np.atleast_1d(mlon)), dtype=bool)
        lo = np.where(still, mid, lo)
        hi = np.where(still, hi, mid)
    return (lo + hi) / 2


def unit_vectors(lat, lon):
    phi, lam = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)], axis=-1)


def mean_position(lat, lon):
    """Centre of a cluster of points: the mean of their unit vectors, so it works across the
    antimeridian and near the poles."""
    v = unit_vectors(lat, lon).mean(axis=0)
    return float(np.degrees(np.arctan2(v[2], np.hypot(v[0], v[1])))), float(
        np.degrees(np.arctan2(v[1], v[0]))
    )
