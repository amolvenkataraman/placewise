"""Cleaning steps: pure functions Track -> new Track that drop, reorder or regroup points. Segments
follow the points that survive (see `Track.__getitem__`), meta is carried over, and inputs are
never modified. Smoothing lives in `smoothing`.
"""

import time as _clock
from bisect import bisect_left, bisect_right

import numpy as np

from placewise.constants.tracks import (
    CLOCK_JUMP_MAX_OFFSET_S,
    FUTURE_TOLERANCE_S,
    GAP_SPLIT_S,
    MIN_PLAUSIBLE_TIME,
    SPIKE_MAX_POINTS,
    SPIKE_MAX_SPEED_KMH,
    SPIKE_MIN_JUMP_M,
    THIN_EVERY_M,
    THIN_EVERY_S,
)
from placewise.geo.distances import haversine

from .._ops import M_PER_KM, bounds, columns, leg_metres, segment_ids, speed
from ..track import Track


def sort_and_dedupe(track):
    """Points in time order, with exact duplicate (time, lat, lon) rows reduced to their first
    occurrence. Points sharing a time but not a position are kept, in their recorded order."""
    if len(track) == 0:
        return track[:]
    t, lat, lon = track.time, track.lat, track.lon
    order = np.lexsort((lon, lat, t))  # stable, so the first occurrence leads each duplicate run
    ts, las, los = t[order], lat[order], lon[order]
    dup = np.r_[False, (ts[1:] == ts[:-1]) & (las[1:] == las[:-1]) & (los[1:] == los[:-1])]
    first = order[~dup]
    return track[first[np.lexsort((first, t[first]))]]


def drop_invalid(track, min_time=MIN_PLAUSIBLE_TIME, max_time=None):
    """Drop points with a NaN or exactly (0, 0) position (the "null island" a logger writes before
    its first fix) or a time that is NaN or outside [min_time, max_time]. max_time defaults to a
    day past now."""
    if max_time is None:
        max_time = _clock.time() + FUTURE_TOLERANCE_S
    t, lat, lon = track.time, track.lat, track.lon
    with np.errstate(invalid="ignore"):
        ok = (
            np.isfinite(lat)
            & np.isfinite(lon)
            & ~((lat == 0) & (lon == 0))
            & np.isfinite(t)
            & (t >= min_time)
            & (t <= max_time)
        )
    return track[ok]


def filter_accuracy(track, max_m):
    """Drop points whose reported accuracy is worse than max_m metres. Points with no accuracy
    (NaN, or no accuracy column at all) are kept: unknown is not bad."""
    if track.accuracy is None:
        return track[:]
    with np.errstate(invalid="ignore"):
        return track[~(track.accuracy > max_m)]


def remove_spikes(
    track, max_speed_kmh=SPIKE_MAX_SPEED_KMH, min_jump_m=SPIKE_MIN_JUMP_M, max_points=SPIKE_MAX_POINTS
):
    """Drop out-and-back excursions: a run of up to max_points points that is reached and left by
    legs longer than min_jump_m and faster than max_speed_kmh, while the points either side of it
    (in the same segment) agree with each other, i.e. travelling between them directly is
    plausible. Single points are tried first; the search repeats until nothing changes, since
    removing one spike can expose another.

    A segment's first and last points have only one neighbour, so they are never judged spikes."""
    keep = np.arange(len(track))
    lat, lon, t, seg = track.lat, track.lon, track.time, segment_ids(track)
    max_ms = max_speed_kmh / 3.6
    changed = True
    while changed:
        changed = False
        la, lo, tt, sg = lat[keep], lon[keep], t[keep], seg[keep]
        if len(la) < 3:
            break
        # entry and exit legs of any run are consecutive legs, so one pass of leg distances
        # flags them all; only the few candidates then need their bypass checked
        legs = leg_metres(la, lo)
        jump = (legs > min_jump_m) & (speed(legs, np.diff(tt)) > max_ms)
        for size in range(1, max_points + 1):
            starts = _spike_runs(la, lo, tt, sg, jump, size, max_ms)
            if starts:
                drop = np.concatenate([np.arange(s, s + size) for s in starts])
                keep = np.delete(keep, drop)
                changed = True
                break  # re-check shorter runs first on what is left
    return track[keep]


def _spike_runs(lat, lon, t, seg, jump, size, max_ms):
    """Start indices of non-overlapping spike runs of `size` points; jump[k] flags leg k -> k+1
    as long and impossibly fast."""
    if len(jump) <= size:
        return []
    a = np.flatnonzero(jump[:-size] & jump[size:])  # the point before each candidate run
    b = a + size + 1
    a, b = a[seg[a] == seg[b]], b[seg[a] == seg[b]]
    d_by = np.asarray(haversine(lat[a], lon[a], lat[b], lon[b])) * M_PER_KM
    a = a[speed(d_by, t[b] - t[a]) <= max_ms]
    starts, end = [], -2
    # greedy left to right, leaving each accepted run's neighbours alone this round: in an
    # alternating A B A B pattern only the first B can be told apart with confidence
    for s in (a + 1).tolist():
        if s > end + 1:
            starts.append(s)
            end = s + size - 1
    return starts


def split_gaps(track, max_gap_s=GAP_SPLIT_S, max_jump_m=None):
    """Start a new segment wherever consecutive points are more than max_gap_s seconds apart or
    (when given) more than max_jump_m metres apart. Existing segment starts are kept; either test
    can be switched off with None."""
    n = len(track)
    if n < 2:
        return track[:]
    brk = np.zeros(n - 1, dtype=bool)
    if max_gap_s is not None:
        brk |= np.diff(track.time) > max_gap_s
    if max_jump_m is not None:
        brk |= leg_metres(track.lat, track.lon) > max_jump_m
    starts = sorted(set(track.segments) | {int(i) + 1 for i in np.flatnonzero(brk)})
    return Track.from_columns(columns(track), starts, track.meta)


def fix_clock_jumps(track, max_offset_s=CLOCK_JUMP_MAX_OFFSET_S):
    """Drop points with a broken clock, keeping the recorded order: first those further than
    max_offset_s (plus twice the interquartile time span, so long recordings keep their ends) from
    the median time, then the fewest points needed for time never to run backwards (the longest
    non-decreasing run of times survives, so one bad point costs one point, whichever way it
    jumped)."""
    t = track.time
    finite = np.isfinite(t)
    if not finite.any():
        return track[finite]
    q25, median, q75 = np.percentile(t[finite], [25, 50, 75])
    with np.errstate(invalid="ignore"):
        idx = np.flatnonzero(finite & (np.abs(t - median) <= max_offset_s + 2 * (q75 - q25)))
    times = t[idx]
    if np.any(np.diff(times) < 0):
        idx = idx[_longest_non_decreasing(times)]
    return track[idx]


def _longest_non_decreasing(values):
    """Indices of a longest non-decreasing subsequence (patience sorting, O(n log n))."""
    tails, tails_at, prev = [], [], [-1] * len(values)
    for i, v in enumerate(values.tolist()):
        k = bisect_right(tails, v)
        if k == len(tails):
            tails.append(v)
            tails_at.append(i)
        else:
            tails[k], tails_at[k] = v, i
        prev[i] = tails_at[k - 1] if k else -1
    out, i = [], tails_at[-1]
    while i >= 0:
        out.append(i)
        i = prev[i]
    return np.array(out[::-1], dtype=np.intp)


def thin(track, every_s=THIN_EVERY_S, every_m=THIN_EVERY_M):
    """Keep a point once every_s seconds or every_m metres (along the path) have passed since the
    last kept one, whichever comes first, plus the first and last point of every segment. Either
    criterion can be switched off with None."""
    n = len(track)
    if n == 0:
        return track[:]
    # cumulative time and distance never decrease, so each next kept point is a binary search
    # away and the loop runs once per kept point, not once per point
    cum_t = np.maximum.accumulate(track.time).tolist()
    cum_d = np.r_[0.0, np.cumsum(leg_metres(track.lat, track.lon))].tolist()
    keep = []
    for start, end in bounds(track):
        j = start
        keep.append(j)
        while True:
            nxt = end
            if every_s is not None:
                nxt = min(nxt, bisect_left(cum_t, cum_t[j] + every_s, j + 1, end))
            if every_m is not None:
                nxt = min(nxt, bisect_left(cum_d, cum_d[j] + every_m, j + 1, end))
            if nxt >= end - 1:
                break
            keep.append(nxt)
            j = nxt
        if end - 1 > start:
            keep.append(end - 1)
    return track[np.array(keep, dtype=np.intp)]
