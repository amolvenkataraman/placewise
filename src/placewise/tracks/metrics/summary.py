"""Summary statistics of a track: distance, moving and stopped time, speeds, elevation gain and
loss, heart rate and power.

Distances are haversine legs between consecutive fixes. Legs that cross from one segment to the
next are gaps in the recording: they add no distance and no moving or stopped time (elapsed
`duration_s` still spans them). Run `clean` first on raw data; jitter inflates distance.
"""

from dataclasses import dataclass

import numpy as np

from placewise.constants.tracks import ELEVATION_HYSTERESIS_M, MAX_SPEED_WINDOW, MOVING_SPEED_KMH
from placewise.model._base import Model

from .._ops import M_PER_KM, bounds, leg_metres, nanmedian_rows, point_weights, segment_ids, speed, windows
from .._ops import in_segment_steps as within_legs

_KMH = 3.6  # (km/h) / (m/s)


@dataclass(frozen=True, slots=True)
class TrackStats(Model):
    """Summary of a track. Times in seconds: duration_s is elapsed (first to last fix, gaps
    included); moving_time_s + stopped_time_s is the recorded time inside segments.
    avg_speed_kmh is distance over that recorded time. Columns the track lacks give None."""

    distance_km: float
    duration_s: float
    moving_time_s: float
    stopped_time_s: float
    avg_speed_kmh: float
    avg_moving_speed_kmh: float
    max_speed_kmh: float
    points: int
    segments: int
    distance_3d_km: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    min_ele_m: float | None = None
    max_ele_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    avg_power: float | None = None


def stats(track, moving_speed_kmh=MOVING_SPEED_KMH, elevation_threshold_m=ELEVATION_HYSTERESIS_M):
    """Summary statistics (see TrackStats).

    A leg is moving when its speed reaches moving_speed_kmh: the mean of the device `speed` at its
    two ends when the track has one (Doppler speed shrugs off position jitter), else distance over
    time. max_speed_kmh is the device's top speed when present, else the largest rolling median
    of MAX_SPEED_WINDOW consecutive leg speeds, so one bad fix can't set it. Elevation gain and
    loss count only climbs and descents of at least elevation_threshold_m (hysteresis)."""
    n = len(track)
    if n == 0:
        return TrackStats(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)
    t = track.time
    inside = within_legs(track)
    legs, dt = leg_metres(track.lat, track.lon), np.diff(t)
    leg_v = speed(legs, dt)
    if track.speed is not None:
        device = (track.speed[:-1] + track.speed[1:]) / 2
        leg_v = np.where(np.isfinite(device), device, leg_v)
    moving = inside & (leg_v >= moving_speed_kmh / _KMH)

    distance = float(np.sum(legs[inside]))
    recorded = float(np.sum(dt[inside]))
    moving_time = float(np.sum(dt[moving]))
    moving_distance = float(np.sum(legs[moving]))

    ele = track.ele
    elevation = {}
    if ele is not None and np.isfinite(ele).any():
        dz = np.diff(ele)
        legs_3d = np.where(np.isfinite(dz), np.hypot(legs, dz), legs)
        gain = loss = 0.0
        for start, end in bounds(track):
            e = ele[start:end]
            g, lo = _hysteresis(e[np.isfinite(e)], elevation_threshold_m)
            gain, loss = gain + g, loss + lo
        elevation = {
            "distance_3d_km": float(np.sum(legs_3d[inside])) / M_PER_KM,
            "elevation_gain_m": gain,
            "elevation_loss_m": loss,
            "min_ele_m": float(np.nanmin(ele)),
            "max_ele_m": float(np.nanmax(ele)),
        }
    weights = point_weights(track, inside)
    return TrackStats(
        distance_km=distance / M_PER_KM,
        duration_s=float(t[-1] - t[0]),
        moving_time_s=moving_time,
        stopped_time_s=recorded - moving_time,
        avg_speed_kmh=distance / recorded * _KMH if recorded > 0 else 0.0,
        avg_moving_speed_kmh=moving_distance / moving_time * _KMH if moving_time > 0 else 0.0,
        max_speed_kmh=_max_speed(track, legs, dt, inside) * _KMH,
        points=n,
        segments=len(track.segments),
        **elevation,
        avg_hr=_weighted_mean(track.hr, weights),
        max_hr=_nanmax(track.hr),
        avg_power=_weighted_mean(track.power, weights),
    )


def _max_speed(track, legs, dt, inside):
    if track.speed is not None and np.isfinite(track.speed).any():
        return float(np.nanmax(track.speed))
    if not inside.any():
        return 0.0
    leg_v = np.where(inside, speed(legs, dt), np.nan)
    # legs that cross a gap get their own group so no window reaches over one
    groups = np.where(inside, segment_ids(track)[:-1], -2 - np.arange(len(legs)))
    smoothed = nanmedian_rows(windows(leg_v, groups, MAX_SPEED_WINDOW))
    return float(np.nanmax(smoothed)) if np.isfinite(smoothed).any() else 0.0


def _hysteresis(e, threshold):
    """(gain, loss) counting a climb or descent only once it has gone threshold metres, then in
    full from its turning point, so noise smaller than the threshold adds nothing and the real
    climbs lose nothing."""
    if len(e) < 2:
        return 0.0, 0.0
    # only turning points matter: the extremes and the order they come in
    e = e[np.r_[True, np.diff(e) != 0]]
    if len(e) > 2:
        step = np.sign(np.diff(e))
        e = e[np.r_[True, step[1:] != step[:-1], True]]
    gain = loss = 0.0
    values = e.tolist()
    low = high = values[0]
    direction, anchor, peak = 0, values[0], values[0]
    for v in values[1:]:
        if direction == 0:  # not yet moved threshold metres from everything seen so far
            low, high = min(low, v), max(high, v)
            if v - low >= threshold:
                direction, anchor, peak = 1, low, v
            elif high - v >= threshold:
                direction, anchor, peak = -1, high, v
        elif direction == 1:
            if v > peak:
                peak = v
            elif peak - v >= threshold:
                gain += peak - anchor
                direction, anchor, peak = -1, peak, v
        elif v < peak:
            peak = v
        elif v - peak >= threshold:
            loss += anchor - peak
            direction, anchor, peak = 1, peak, v
    if direction == 1:
        gain += peak - anchor
    elif direction == -1:
        loss += anchor - peak
    return gain, loss


def _weighted_mean(values, weights):
    if values is None:
        return None
    ok = np.isfinite(values)
    if not ok.any():
        return None
    w = weights[ok]
    return float(np.sum(values[ok] * w) / np.sum(w)) if np.sum(w) > 0 else float(np.mean(values[ok]))


def _nanmax(values):
    return float(np.nanmax(values)) if values is not None and np.isfinite(values).any() else None
