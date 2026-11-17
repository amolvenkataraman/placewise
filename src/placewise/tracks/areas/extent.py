"""A track against points and its own extent: the closest pass to a point, and the bounding box.

The closest pass is measured on the great-circle steps between fixes, never across a segment
break. Track times must be non-decreasing.
"""

from typing import NamedTuple

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo.distances import haversine
from placewise.geo.lines import _nearest_on_arcs
from placewise.model import BBox

from .._ops import in_segment_steps, require_sorted, step_km, unit_vectors


class ClosestPass(NamedTuple):
    time: float
    distance_km: float
    index: int  # the fix at or just before the closest point


def closest_pass(track, lat, lon):
    """ClosestPass(time, distance_km, index): where the track came nearest to (lat, lon), on the
    great-circle steps between fixes (never across a segment break), with the time interpolated
    along the step. `index` is the fix at or just before that point."""
    require_sorted(track)
    n = len(track)
    if n == 0:
        raise ValueError("an empty track has no closest pass")
    t, tlat, tlon = track.time, track.lat, track.lon
    to_fix = np.asarray(haversine(lat, lon, tlat, tlon), dtype=np.float64).reshape(-1)
    best = int(np.argmin(to_fix))
    result = ClosestPass(float(t[best]), float(to_fix[best]), best)
    if n < 2:
        return result
    # every point of a step is within half its length of an end, so only steps whose nearer end
    # is within (best fix distance + half the step) can beat the best fix
    near_end = np.minimum(to_fix[:-1], to_fix[1:])
    steps = np.flatnonzero(in_segment_steps(track) & (near_end - step_km(track) / 2 <= result.distance_km))
    if not len(steps):
        return result
    p = unit_vectors(np.float64(lat), np.float64(lon))[None, None, :]
    a, b = unit_vectors(tlat[steps], tlon[steps]), unit_vectors(tlat[steps + 1], tlon[steps + 1])
    _, angle, fraction = _nearest_on_arcs(p, a, b)
    k = int(np.argmin(angle[0]))
    distance = float(angle[0, k] * MEAN_RADIUS_KM)
    if distance < result.distance_km:
        s, f = int(steps[k]), float(fraction[0, k])
        return ClosestPass(float(t[s] + f * (t[s + 1] - t[s])), distance, s + 1 if f >= 1.0 else s)
    return result


def bbox(track):
    """Smallest BBox around every fix. A track crossing the antimeridian gets a box with west >
    east (the GeoJSON convention) rather than one spanning the globe."""
    if len(track) == 0:
        raise ValueError("an empty track has no bounding box")
    lat = track.lat
    lons = np.unique(track.lon)
    # the box is the circle of longitudes minus its widest empty stretch
    gaps = np.diff(lons)
    wrap = lons[0] + 360.0 - lons[-1]
    if not len(gaps) or wrap >= gaps.max():
        west, east = lons[0], lons[-1]
    else:
        k = int(np.argmax(gaps))
        west, east = lons[k + 1], lons[k]
    return BBox(float(lat.min()), float(west), float(lat.max()), float(east))
