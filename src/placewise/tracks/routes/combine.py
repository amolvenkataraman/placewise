"""Putting tracks together and taking them apart: concat, merge, split, crop and reverse.

Pure functions; inputs are never modified. Where tracks with different optional columns are
combined, the result has every column any of them had, NaN where a track lacked it. Metadata is
the first track's, with any field it leaves empty filled in when every other track that sets it
agrees (pass `meta=` to choose it yourself).
"""

import dataclasses
from itertools import pairwise

import numpy as np

from placewise.constants.tracks import GAP_SPLIT_S, MERGE_DUPLICATE_M, MERGE_WINDOW_S
from placewise.geo.distances import haversine

from .._ops import M_PER_KM, require_sorted
from ..track import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, Track

_DAY_S = 86_400
_SPLIT_BY = ("segment", "day", "gap")
_PREFER = ("accuracy", "density")


def concat(tracks, allow_overlap=False, meta=None):
    """One Track from several, each input's segments becoming segments of the result. Inputs are
    placed in order of their first fix (ties keep the given order) and must not overlap in time:
    one may start the moment the previous one ends. With allow_overlap=True overlapping inputs are
    concatenated anyway, so time runs backwards at the segment where the next one starts; to
    interleave simultaneous recordings into one time-ordered track use `merge`. Empty inputs are
    skipped."""
    tracks = list(tracks)
    if not tracks:
        raise ValueError("concat needs at least one track")
    out_meta = meta if meta is not None else _merged_meta([t.meta for t in tracks])
    names = _union_columns(tracks)
    # sorted() is stable, so equal start times keep the caller's order
    parts = sorted((t for t in tracks if len(t)), key=lambda t: _span(t)[0])
    if not parts:
        return Track.from_columns({name: np.zeros(0) for name in names}, None, out_meta)
    if not allow_overlap:
        end = -np.inf
        for t in parts:
            start, stop = _span(t)
            if start < end:
                raise ValueError(
                    "tracks overlap in time; pass allow_overlap=True to concatenate them anyway, "
                    "or merge() to interleave them"
                )
            end = max(end, stop)
    starts, offset = [], 0
    for t in parts:
        starts += [offset + s for s in t.segments]
        offset += len(t)
    columns = {name: np.concatenate([_column(t, name) for t in parts]) for name in names}
    return Track.from_columns(columns, starts, out_meta)


def merge(
    tracks,
    prefer="accuracy",
    window_s=MERGE_WINDOW_S,
    duplicate_m=MERGE_DUPLICATE_M,
    max_gap_s=GAP_SPLIT_S,
    meta=None,
):
    """One time-ordered Track from recordings of the same period by several devices (a phone and a
    watch, say).

    Time is cut into windows of window_s seconds; in a window more than one source recorded, only
    the better source's fixes are kept. prefer="accuracy" picks the lower mean `accuracy` when
    every competing source reports one in that window, and otherwise falls back to sampling
    density (more fixes wins); prefer="density" always uses density. Remaining ties go to the
    source listed first. window_s=None keeps every source everywhere.

    Then fixes from different sources in the same whole second and less than duplicate_m metres
    apart are near-duplicates: the less accurate one is dropped (the later-listed source's, when
    accuracy can't tell). A single source's fixes are never deduplicated against each other.

    The input segments are not carried over: a segment starts wherever consecutive merged fixes
    are more than max_gap_s seconds apart (None: never). Fixes without a time are dropped."""
    if prefer not in _PREFER:
        raise ValueError(f"prefer must be one of {_PREFER}, not {prefer!r}")
    tracks = list(tracks)
    if not tracks:
        raise ValueError("merge needs at least one track")
    out_meta = meta if meta is not None else _merged_meta([t.meta for t in tracks])
    names = _union_columns(tracks)
    columns = {name: np.concatenate([_column(t, name) for t in tracks]) for name in names}
    source = np.repeat(np.arange(len(tracks)), [len(t) for t in tracks])
    timed = np.isfinite(columns["time"])
    columns, source = {k: v[timed] for k, v in columns.items()}, source[timed]
    # time order; equal times go by source priority, then by recorded order
    order = np.lexsort((np.arange(len(source)), source, columns["time"]))
    columns, source = {k: v[order] for k, v in columns.items()}, source[order]
    t, accuracy = columns["time"], columns.get("accuracy")

    keep = np.ones(len(t), dtype=bool)
    if window_s is not None and len(tracks) > 1 and len(t):
        keep = _best_source_per_window(t, source, accuracy, float(window_s), prefer, len(tracks))
    if duplicate_m is not None and len(tracks) > 1:
        kept = np.flatnonzero(keep)
        sub_acc = None if accuracy is None else accuracy[kept]
        dup = _near_duplicates(
            t[kept], columns["lat"][kept], columns["lon"][kept], source[kept], sub_acc, duplicate_m
        )
        keep[kept[dup]] = False

    columns = {k: v[keep] for k, v in columns.items()}
    starts = [0]
    if max_gap_s is not None and len(columns["time"]) > 1:
        starts += (np.flatnonzero(np.diff(columns["time"]) > max_gap_s) + 1).tolist()
    return Track.from_columns(columns, starts if len(columns["time"]) else None, out_meta)


def _best_source_per_window(t, source, accuracy, window_s, prefer, n_sources):
    """For each fix, whether its source is the one kept in its time window."""
    window = np.floor((t - t[0]) / window_s).astype(np.int64)  # t is sorted, t[0] the earliest
    groups, inverse = np.unique(window * n_sources + source, return_inverse=True)
    count = np.bincount(inverse)
    g_window, g_source = groups // n_sources, groups % n_sources
    primary = np.zeros(len(groups))
    if prefer == "accuracy" and accuracy is not None:
        known = np.isfinite(accuracy)
        total = np.bincount(inverse, weights=np.where(known, accuracy, 0.0))
        n_known = np.bincount(inverse, weights=known.astype(np.float64))
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = total / n_known
        # accuracies only settle a window where every competing source reports one; a source
        # that doesn't can't be judged against one that does
        _, w_inverse = np.unique(g_window, return_inverse=True)
        all_known = np.ones(w_inverse.max() + 1, dtype=bool)
        np.logical_and.at(all_known, w_inverse, np.isfinite(mean))
        primary = np.where(all_known[w_inverse], mean, 0.0)
    rank = np.lexsort((g_source, -count, primary, g_window))
    first = rank[np.r_[True, g_window[rank][1:] != g_window[rank][:-1]]]
    chosen = np.zeros(len(groups), dtype=bool)
    chosen[first] = True
    return chosen[inverse]


def _near_duplicates(t, lat, lon, source, accuracy, duplicate_m):
    """Which fixes (sorted by time) repeat a fix from another source in the same whole second."""
    n = len(t)
    second = np.floor(t)
    drop = np.zeros(n, dtype=bool)
    k = 1
    # compare each fix with the next, the one after ... while any pair still shares a second
    while k < n and np.any(second[k:] == second[:-k]):
        a = np.flatnonzero((second[k:] == second[:-k]) & (source[k:] != source[:-k]))
        b = a + k
        close = np.asarray(haversine(lat[a], lon[a], lat[b], lon[b])) * M_PER_KM < duplicate_m
        for i, j in zip(a[close].tolist(), b[close].tolist(), strict=True):
            if not (drop[i] or drop[j]):
                drop[_worse(i, j, source, accuracy)] = True
        k += 1
    return drop


def _worse(i, j, source, accuracy):
    a = (accuracy[i], accuracy[j]) if accuracy is not None else (np.nan, np.nan)
    if np.isfinite(a[0]) and np.isfinite(a[1]) and a[0] != a[1]:
        return i if a[0] > a[1] else j
    return i if source[i] > source[j] else j


def split(track, by="segment", tz_offset_s=0, max_gap_s=GAP_SPLIT_S):
    """A list of Tracks. by="segment": one per segment. by="day": one per local calendar day, days
    being UTC shifted by tz_offset_s (seconds east of UTC; one number or one per fix). by="gap":
    a new piece wherever consecutive fixes are more than max_gap_s seconds apart. Segment breaks
    inside a piece are kept. Times must be non-decreasing for "day" and "gap"."""
    if by not in _SPLIT_BY:
        raise ValueError(f"by must be one of {_SPLIT_BY}, not {by!r}")
    n = len(track)
    if n == 0:
        return []
    if by == "segment":
        return list(track.iter_segments())
    require_sorted(track)
    if by == "day":
        day = np.floor((track.time + np.asarray(tz_offset_s, dtype=np.float64)) / _DAY_S)
        cuts = np.flatnonzero(day[1:] != day[:-1]) + 1
    else:
        cuts = np.flatnonzero(np.diff(track.time) > max_gap_s) + 1
    return [track[a:b] for a, b in pairwise([0, *cuts.tolist(), n])]


def crop(track, start=None, end=None):
    """The fixes with start <= time <= end (UTC unix seconds; None leaves that side open).
    Segments follow the fixes that remain."""
    t = track.time
    keep = np.ones(len(t), dtype=bool)
    with np.errstate(invalid="ignore"):
        if start is not None:
            keep &= t >= start
        if end is not None:
            keep &= t <= end
    return track[keep]


def reverse(track):
    """The track travelled backwards, for using a recorded route the other way. Fixes and segments
    run in reverse order and `heading` turns round by 180°. Times are mirrored within the track's
    span (new time = first + last - old time), so they still increase, start and end where the
    original did and keep each step's duration, now in reverse order; they are not times anyone
    was at those places. Other columns (speed, heart rate ...) stay with their fix."""
    n = len(track)
    if n == 0:
        return track[:]
    columns = {name: getattr(track, name)[::-1] for name in track.columns}
    t = columns["time"]
    if np.isfinite(t).any():
        columns["time"] = (np.nanmin(t) + np.nanmax(t)) - t
    if "heading" in columns:
        columns["heading"] = (columns["heading"] + 180.0) % 360.0
    starts = sorted(n - end for end in (*track.segments[1:], n))
    return Track.from_columns(columns, starts, track.meta)


def _union_columns(tracks):
    present = {name for t in tracks for name in t.columns}
    return [name for name in REQUIRED_COLUMNS + OPTIONAL_COLUMNS if name in present]


def _column(track, name):
    values = getattr(track, name)
    return np.full(len(track), np.nan) if values is None else values


def _span(track):
    t = track.time
    finite = t[np.isfinite(t)]
    return (float(finite.min()), float(finite.max())) if len(finite) else (np.inf, -np.inf)


def _merged_meta(metas):
    """The first meta, each field it leaves empty taken from the others when they all agree."""
    first = metas[0]
    values = {}
    for field in dataclasses.fields(first):
        mine = getattr(first, field.name)
        others = {getattr(m, field.name) for m in metas} - {None}
        values[field.name] = mine if mine is not None or len(others) != 1 else others.pop()
    return dataclasses.replace(first, **values)
