"""Helpers shared by the track operations: legs, segment bookkeeping, rolling windows."""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from placewise.constants.distance import METRES_PER
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


def segment_ids(track):
    starts = np.asarray(track.segments, dtype=np.intp)
    return np.repeat(np.arange(len(starts)), np.diff(np.r_[starts, len(track)]))


def within(track):
    """Per leg (n - 1): True when both ends are in the same segment."""
    mask = np.ones(max(len(track) - 1, 0), dtype=bool)
    mask[np.asarray(track.segments[1:], dtype=np.intp) - 1] = False
    return mask


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
    mask = within(track) if legs_within is None else legs_within
    half = np.where(mask, np.diff(track.time), 0.0) / 2
    w[:-1] += half
    w[1:] += half
    return w
