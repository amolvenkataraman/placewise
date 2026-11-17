"""Cleaning: pure functions Track -> new Track. Segments follow the points that survive (see
`Track.__getitem__`), meta is carried over, and inputs are never modified.

A typical pipeline: drop_invalid -> sort_and_dedupe (or fix_clock_jumps, when the recorded order
is the truth) -> filter_accuracy -> remove_spikes -> split_gaps -> smooth -> thin.
"""

import math
import time as _clock
from bisect import bisect_left, bisect_right

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.tracks import (
    CLOCK_JUMP_MAX_OFFSET_S,
    DEFAULT_ACCURACY_M,
    ELEVATION_WINDOW,
    FUTURE_TOLERANCE_S,
    GAP_SPLIT_S,
    HAMPEL_N_SIGMA,
    KALMAN_PROCESS_NOISE,
    MIN_PLAUSIBLE_TIME,
    SPIKE_MAX_POINTS,
    SPIKE_MAX_SPEED_KMH,
    SPIKE_MIN_JUMP_M,
    THIN_EVERY_M,
    THIN_EVERY_S,
)
from placewise.geo._arrays import wrap_lon
from placewise.geo.distances import haversine

from ._ops import M_PER_KM, bounds, columns, leg_metres, nanmedian_rows, replace, segment_ids, speed, windows
from .track import Track

_M_PER_DEG = math.radians(MEAN_RADIUS_KM * M_PER_KM)
_MAD_TO_SIGMA = 1.4826  # median absolute deviation -> standard deviation, for Gaussian noise
_INITIAL_SPEED_VAR = 1e4  # (100 m/s)²: an all-but-uninformative prior on the starting velocity


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


def smooth(
    track,
    method="kalman",
    process_noise=KALMAN_PROCESS_NOISE,
    default_accuracy_m=DEFAULT_ACCURACY_M,
):
    """Smoothed positions; other columns, segments and meta unchanged.

    "kalman": a constant-velocity Kalman filter followed by a Rauch-Tung-Striebel smoother, run
    per segment in local metres (an equirectangular plane around the segment). Each fix's
    standard error is its `accuracy` when present, else default_accuracy_m; process_noise is the
    random-acceleration spectral density in m²/s³ (larger follows turns more tightly, smaller
    smooths harder). The smoother uses the whole segment, past and future, so it does not lag."""
    if method != "kalman":
        raise ValueError(f"unknown smoothing method {method!r}; use 'kalman'")
    lat, lon = track.lat.copy(), track.lon.copy()
    sigma = np.full(len(track), float(default_accuracy_m))
    if track.accuracy is not None:
        acc = track.accuracy
        sigma = np.where(np.isfinite(acc) & (acc > 0), acc, sigma)
    for start, end in bounds(track):
        if end - start < 2:
            continue
        sl = slice(start, end)
        lat0, lon0 = float(np.mean(lat[sl])), float(lon[start])
        kx = math.cos(math.radians(lat0)) * _M_PER_DEG
        x, y = wrap_lon(lon[sl] - lon0) * kx, (lat[sl] - lat0) * _M_PER_DEG
        xs, ys = _kalman_rts(track.time[sl], x, y, sigma[sl] ** 2, float(process_noise))
        lat[sl] = np.clip(lat0 + ys / _M_PER_DEG, -90.0, 90.0)
        lon[sl] = wrap_lon(lon0 + xs / kx)
    return replace(track, lat=lat, lon=lon)


def _kalman_rts(t, zx, zy, r, q):
    """Smoothed x and y for measurements zx, zy (m) at times t with variances r.

    x and y have independent dynamics and share the measurement variance, so their covariances
    are identical: one 2x2 [position, velocity] covariance recursion serves both axes. The
    recursion is inherently sequential, so it runs on plain floats rather than numpy scalars."""
    n = len(t)
    t, zx, zy, r = t.tolist(), zx.tolist(), zy.tolist(), r.tolist()
    # start at the first fix, heading as the first leg does (an exact guess on clean data, so a
    # straight path comes back unmoved), with a wide velocity variance so noise there is forgiven
    dt0 = t[1] - t[0]
    vx, vy = ((zx[1] - zx[0]) / dt0, (zy[1] - zy[0]) / dt0) if dt0 > 0 else (0.0, 0.0)
    x, y = zx[0], zy[0]
    p00, p01, p11 = r[0], 0.0, _INITIAL_SPEED_VAR
    fx, fvx, fy, fvy = [x], [vx], [y], [vy]  # filtered states
    f00, f01, f11 = [p00], [p01], [p11]  # filtered covariances
    a00s, a01s, a11s = [0.0], [0.0], [0.0]  # predicted covariances (index k: predicted for k)
    for k in range(1, n):
        dt = t[k] - t[k - 1]
        x += dt * vx
        y += dt * vy
        qdt = q * dt
        a00 = p00 + dt * (2 * p01 + dt * p11) + qdt * dt * dt / 3
        a01 = p01 + dt * p11 + qdt * dt / 2
        a11 = p11 + qdt
        s = a00 + r[k]
        k0, k1 = a00 / s, a01 / s
        ix, iy = zx[k] - x, zy[k] - y
        x += k0 * ix
        vx += k1 * ix
        y += k0 * iy
        vy += k1 * iy
        p00, p01, p11 = (1 - k0) * a00, (1 - k0) * a01, a11 - k1 * a01
        fx.append(x)
        fvx.append(vx)
        fy.append(y)
        fvy.append(vy)
        f00.append(p00)
        f01.append(p01)
        f11.append(p11)
        a00s.append(a00)
        a01s.append(a01)
        a11s.append(a11)

    # RTS gains C_k = P_k F^T inv(P_pred_{k+1}) depend only on covariances: compute them at once
    dt = np.diff(np.asarray(t))
    f00_, f01_, f11_ = (np.asarray(v[:-1]) for v in (f00, f01, f11))
    a00_, a01_, a11_ = (np.asarray(v[1:]) for v in (a00s, a01s, a11s))
    det = a00_ * a11_ - a01_ * a01_
    b00, b01, b10, b11 = f00_ + dt * f01_, f01_, f01_ + dt * f11_, f11_
    c00 = ((b00 * a11_ - b01 * a01_) / det).tolist()
    c01 = ((b01 * a00_ - b00 * a01_) / det).tolist()
    c10 = ((b10 * a11_ - b11 * a01_) / det).tolist()
    c11 = ((b11 * a00_ - b10 * a01_) / det).tolist()
    dt = dt.tolist()

    sx, svx, sy, svy = fx[-1], fvx[-1], fy[-1], fvy[-1]
    out_x, out_y = [0.0] * n, [0.0] * n
    out_x[-1], out_y[-1] = sx, sy
    for k in range(n - 2, -1, -1):
        h = dt[k]
        ex, evx = sx - (fx[k] + h * fvx[k]), svx - fvx[k]  # smoothed minus predicted, at k + 1
        ey, evy = sy - (fy[k] + h * fvy[k]), svy - fvy[k]
        sx = fx[k] + c00[k] * ex + c01[k] * evx
        svx = fvx[k] + c10[k] * ex + c11[k] * evx
        sy = fy[k] + c00[k] * ey + c01[k] * evy
        svy = fvy[k] + c10[k] * ey + c11[k] * evy
        out_x[k], out_y[k] = sx, sy
    return np.array(out_x), np.array(out_y)


def smooth_elevation(track, window=ELEVATION_WINDOW, n_sigma=HAMPEL_N_SIGMA):
    """Elevation outliers replaced, per segment, by a Hampel filter: a point further than n_sigma
    robust standard deviations from the median of the `window` points centred on it (odd) takes
    that median. n_sigma=None gives a plain running median instead. NaN stays NaN; a track
    without elevation comes back unchanged."""
    if window < 1 or window % 2 == 0:
        raise ValueError(f"window must be a positive odd number of points, not {window}")
    ele = track.ele
    if ele is None or len(track) == 0:
        return track[:]
    w = windows(ele, segment_ids(track), window)
    med = nanmedian_rows(w)
    if n_sigma is None:
        new = np.where(np.isnan(ele), ele, med)
    else:
        mad = nanmedian_rows(np.abs(w - med[:, None]))
        with np.errstate(invalid="ignore"):
            new = np.where(np.abs(ele - med) > n_sigma * _MAD_TO_SIGMA * mad, med, ele)
    return replace(track, ele=new)


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
