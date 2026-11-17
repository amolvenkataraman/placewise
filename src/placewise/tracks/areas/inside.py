"""A track against areas: time spent inside one, and crossings from one to another.

Where a step between two fixes crosses an area's edge, the crossing is located by bisection along
the great circle between them and its time interpolated at constant speed. Steps across a segment
break are never interpolated. Track times must be non-decreasing.
"""

from typing import NamedTuple

import numpy as np

from placewise.geo.polygon_index import PolygonIndex

from .._ops import bisect_change, in_segment_steps, require_sorted


class Crossing(NamedTuple):
    time: float
    from_index: int  # index into the features, -1 for none
    to_index: int


def time_inside(track, shape):
    """Seconds the track spent inside `shape` (a Feature, an Outline or anything with a vectorised
    `contains(lat, lon)`). Each step inside a segment counts in full when both fixes are inside,
    and up to or from the edge when it crosses one; steps across a segment break count nothing."""
    require_sorted(track)
    if len(track) < 2:
        return 0.0
    lat, lon = track.lat, track.lon
    inside = np.asarray(shape.contains(lat, lon), dtype=bool)
    steps = in_segment_steps(track)
    dt_s = np.diff(track.time)
    total = float(dt_s[steps & inside[:-1] & inside[1:]].sum())
    edge = np.flatnonzero(steps & (inside[:-1] != inside[1:]))
    if len(edge):
        began_inside = inside[edge]
        f = bisect_change(
            lat[edge],
            lon[edge],
            lat[edge + 1],
            lon[edge + 1],
            lambda la, lo: np.asarray(shape.contains(la, lo), dtype=bool) == began_inside,
        )
        total += float(np.sum(np.where(began_inside, f, 1.0 - f) * dt_s[edge]))
    return total


def crossings(track, features):
    """Every change of containing feature along the track, as Crossing(time, from_index,
    to_index) in time order; -1 stands for outside every feature, and where features overlap
    the first one counts. `features` is a list of Features or a ready PolygonIndex.

    The time is interpolated to where the step leaves its starting feature; if a step passes
    through a third feature on the way, one crossing straight to the step's end feature is
    reported. A change across a segment break is reported at the first fix after the break,
    the earliest the track knows of it."""
    require_sorted(track)
    if len(track) < 2:
        return []
    index = features if isinstance(features, PolygonIndex) else PolygonIndex(features)
    lat, lon, t = track.lat, track.lon, track.time
    where = np.atleast_1d(index.query(lat, lon))
    change = np.flatnonzero(where[1:] != where[:-1])
    if not len(change):
        return []
    times = t[change + 1].astype(np.float64)
    steps = in_segment_steps(track)[change]
    if steps.any():
        k = change[steps]
        origin = where[k]
        f = bisect_change(
            lat[k],
            lon[k],
            lat[k + 1],
            lon[k + 1],
            lambda la, lo: np.atleast_1d(index.query(la, lo)) == origin,
        )
        times[steps] = t[k] + f * (t[k + 1] - t[k])
    return [
        Crossing(float(time), int(a), int(b))
        for time, a, b in zip(times, where[change], where[change + 1], strict=True)
    ]
