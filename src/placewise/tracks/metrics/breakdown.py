"""Breakdowns along a track: split tables, best efforts, pace, grade and heart-rate zones.

Distances are haversine legs between consecutive fixes inside one segment; gaps between segments
add neither distance nor time. Boundaries (a split's end, a best effort's ends, a grade window's
edges) are interpolated inside the leg that crosses them.
"""

import math
from dataclasses import dataclass

import numpy as np

from placewise.constants.tracks import BEST_EFFORT_KM, GRADE_WINDOW_M, HR_ZONES, SPLIT_KM
from placewise.geo._arrays import as_floats, out
from placewise.model._base import Model

from .._ops import M_PER_KM, bounds, leg_metres, point_weights
from .._ops import in_segment_steps as within_legs


@dataclass(frozen=True, slots=True)
class Split(Model):
    """One row of a split table: `index` from 1, `end_km` the cumulative distance at its end,
    duration_s the recorded time it took (stops included, gaps excluded)."""

    index: int
    end_km: float
    distance_km: float
    duration_s: float
    pace_s_per_km: float
    ele_change_m: float | None = None
    avg_hr: float | None = None


@dataclass(frozen=True, slots=True)
class BestEffort(Model):
    distance_km: float
    duration_s: float
    pace_s_per_km: float
    speed_kmh: float
    start_time: float  # unix seconds
    end_time: float


@dataclass(frozen=True, slots=True)
class HrZone(Model):
    """Time in one heart-rate band, low_bpm <= hr < high_bpm; zone 0 is everything below zone 1."""

    index: int
    low_bpm: float
    high_bpm: float
    seconds: float


def _cumulative(track):
    """Cumulative within-segment distance (m) and recorded time (s) at each point; both stay
    flat across a gap between segments."""
    inside = within_legs(track)
    d = np.where(inside, leg_metres(track.lat, track.lon), 0.0)
    dt = np.where(inside, np.diff(track.time), 0.0)
    return np.r_[0.0, np.cumsum(d)], np.r_[0.0, np.cumsum(dt)], inside


def _locate(cum, targets):
    """For each target, (i, f): the point where cum first reaches it lies a fraction f of the way
    from point i - 1 to point i. Targets outside the range clamp to the ends."""
    i = np.clip(np.searchsorted(cum, targets, side="left"), 1, len(cum) - 1)
    lo, hi = cum[i - 1], cum[i]
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(hi > lo, np.clip((targets - lo) / (hi - lo), 0.0, 1.0), np.where(targets > lo, 1.0, 0.0))
    return i, f


def _lerp(values, i, f):
    return values[i - 1] + f * (values[i] - values[i - 1])


def splits(track, every_km=SPLIT_KM):
    """Split table: one Split per every_km of distance plus a final partial one, with each
    boundary interpolated inside the leg that crosses it. avg_hr is time-weighted with heart
    rate interpolated linearly between samples."""
    if len(track) < 2:
        return ()
    cum_d, cum_t, inside = _cumulative(track)
    step, total = every_km * M_PER_KM, cum_d[-1]
    if total <= 0:
        return ()
    marks = step * np.arange(1, math.floor(total / step + 1e-9) + 1)
    if len(marks) == 0 or total - marks[-1] > 1e-3:  # a partial split longer than a millimetre
        marks = np.r_[marks, total]
    edges = np.r_[0.0, marks]
    i, f = _locate(cum_d, edges)
    edge_d = np.minimum(edges, total)
    edge_t = _lerp(cum_t, i, f)
    ele_change = np.diff(_lerp(track.ele, i, f)) if track.ele is not None else None

    avg_hr = None
    if track.hr is not None:
        hr = track.hr
        dt = np.where(inside, np.diff(track.time), 0.0)
        ok = inside & np.isfinite(hr[:-1]) & np.isfinite(hr[1:])
        h0, h1 = np.where(ok, hr[:-1], 0.0), np.where(ok, hr[1:], 0.0)
        cum_h = np.r_[0.0, np.cumsum(dt * (h0 + h1) / 2)]  # integral of hr dt
        cum_w = np.r_[0.0, np.cumsum(np.where(ok, dt, 0.0))]  # seconds with hr
        leg = i - 1  # the leg each edge falls in, entered a fraction f of the way
        a, b, live = h0[leg], h1[leg], ok[leg]
        edge_h = cum_h[leg] + dt[leg] * (f * a + f * f * (b - a) / 2)
        edge_w = cum_w[leg] + np.where(live, dt[leg] * f, 0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            avg_hr = np.diff(edge_h) / np.diff(edge_w)

    rows = []
    for k in range(len(marks)):
        dist_km = (edge_d[k + 1] - edge_d[k]) / M_PER_KM
        duration = float(edge_t[k + 1] - edge_t[k])
        rows.append(
            Split(
                index=k + 1,
                end_km=float(edge_d[k + 1]) / M_PER_KM,
                distance_km=float(dist_km),
                duration_s=duration,
                pace_s_per_km=duration / dist_km if dist_km > 0 else math.inf,
                ele_change_m=None if ele_change is None else float(ele_change[k]),
                avg_hr=None if avg_hr is None or not np.isfinite(avg_hr[k]) else float(avg_hr[k]),
            )
        )
    return tuple(rows)


def best_efforts(track, distances_km=BEST_EFFORT_KM):
    """{distance: BestEffort or None} - the fastest stretch of exactly each distance inside one
    segment, None when no segment is that long.

    Time is linear in distance between fixes, so the time for a stretch is piecewise linear in
    where it starts, with its minimum where the start or the end is on a fix. Both families are
    searched at once (vectorised two-pointer over cumulative distance) with the other end
    interpolated inside its leg."""
    cum_d, _, _ = _cumulative(track)
    result = {}
    for km in distances_km:
        if km <= 0:
            raise ValueError(f"best-effort distances must be positive, not {km}")
        x = km * M_PER_KM
        best = None
        for start, end in bounds(track):
            d = cum_d[start:end] - cum_d[start]
            if len(d) < 2 or d[-1] < x:
                continue
            t = track.time[start:end]
            # ends on a fix, start interpolated
            j = np.flatnonzero(d >= x)
            i = np.minimum(np.searchsorted(d, d[j] - x, side="right") - 1, len(d) - 2)
            t_start = t[i] + (d[j] - x - d[i]) / (d[i + 1] - d[i]) * (t[i + 1] - t[i])
            # starts on a fix, end interpolated
            s = np.flatnonzero(d + x <= d[-1])
            k = np.maximum(np.searchsorted(d, d[s] + x, side="left"), 1)
            t_end = t[k - 1] + (d[s] + x - d[k - 1]) / (d[k] - d[k - 1]) * (t[k] - t[k - 1])
            starts, ends = np.r_[t_start, t[s]], np.r_[t[j], t_end]
            m = int(np.argmin(ends - starts))
            if best is None or ends[m] - starts[m] < best[1] - best[0]:
                best = (float(starts[m]), float(ends[m]))
        if best is None:
            result[km] = None
            continue
        duration = best[1] - best[0]
        result[km] = BestEffort(
            distance_km=float(km),
            duration_s=duration,
            pace_s_per_km=duration / km,
            speed_kmh=km / duration * 3600 if duration > 0 else math.inf,
            start_time=best[0],
            end_time=best[1],
        )
    return result


def pace(speed_kmh):
    """Pace in seconds per km for a speed in km/h (inf when standing still); scalars or arrays."""
    (v,) = as_floats(speed_kmh)
    with np.errstate(divide="ignore"):
        return out(3600.0 / v)


def grade(track, window_m=GRADE_WINDOW_M):
    """Grade in % at each point: elevation change over the window_m of path centred on it
    (clamped at segment ends), NaN where the window covers no distance."""
    if track.ele is None:
        raise ValueError("grade needs an ele column")
    result = np.full(len(track), np.nan)
    cum_d, _, _ = _cumulative(track)
    for start, end in bounds(track):
        if end - start < 2:
            continue
        d, e = cum_d[start:end], track.ele[start:end]
        lo = np.maximum(d - window_m / 2, d[0])
        hi = np.minimum(d + window_m / 2, d[-1])
        e_lo, e_hi = _lerp(e, *_locate(d, lo)), _lerp(e, *_locate(d, hi))
        with np.errstate(divide="ignore", invalid="ignore"):
            result[start:end] = np.where(hi > lo, (e_hi - e_lo) / (hi - lo) * 100, np.nan)
    return result


def hr_zones(track, max_hr=None, zones=HR_ZONES):
    """Seconds in each heart-rate zone. `zones` are the zones' lower bounds as fractions of max_hr
    (default: the track's own maximum); zone 0 collects time below the first. Each sample stands
    for half of each adjacent leg, and gaps between segments count for nothing."""
    if track.hr is None:
        raise ValueError("hr_zones needs an hr column")
    hr = track.hr
    ok = np.isfinite(hr)
    if max_hr is None:
        max_hr = float(np.nanmax(hr)) if ok.any() else math.nan
    edges = np.asarray(zones, dtype=np.float64) * max_hr
    zone_of = np.searchsorted(edges, hr[ok], side="right")
    seconds = np.bincount(zone_of, weights=point_weights(track)[ok], minlength=len(edges) + 1)
    lows, highs = np.r_[0.0, edges], np.r_[edges, math.inf]
    return tuple(
        HrZone(index=k, low_bpm=float(lows[k]), high_bpm=float(highs[k]), seconds=float(seconds[k]))
        for k in range(len(edges) + 1)
    )
