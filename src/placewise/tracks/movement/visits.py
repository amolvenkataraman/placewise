"""Stays and the trips between them: where the traveller stopped, and the movement from one stop
to the next. Track times must be non-decreasing."""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from placewise.constants.tracks import STAY_MAX_BRIDGE_S, STAY_MIN_DURATION_S, STAY_RADIUS_M
from placewise.geo.distances import haversine
from placewise.model._base import Model

from .._ops import in_segment_steps, mean_position, require_sorted, step_km

_SCAN_CHUNK = 64  # first look-ahead when growing a stay; doubles each time it isn't enough


@dataclass(frozen=True, slots=True)
class Stay(Model):
    """Time spent within a radius of one place. Indices are inclusive positions in the track."""

    start: float
    end: float
    lat: float
    lon: float
    n_points: int
    first_index: int
    last_index: int

    @property
    def duration_s(self):
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Trip(Model):
    """The movement from one stay to the next: from its last fix to the next stay's first."""

    start: float
    end: float
    first_index: int
    last_index: int
    n_points: int
    distance_km: float  # along the fixes, leaving out jumps across segment breaks
    origin: Stay
    destination: Stay

    @property
    def duration_s(self):
        return self.end - self.start


def stays(track, radius_m=STAY_RADIUS_M, min_duration_s=STAY_MIN_DURATION_S, max_bridge_s=STAY_MAX_BRIDGE_S):
    """Stay points, as a list of Stay, by the anchor-point method (Li et al. 2008): starting at a
    fix, take every following fix within radius_m of it; if they span at least min_duration_s it is
    a stay, and the search resumes after it; otherwise it resumes at the next fix.

    Silences are bridged: a phone that went quiet and next reported from the same place stayed
    there, so two fixes hours apart within the radius make a stay even across a segment break.
    Silences longer than max_bridge_s are not bridged.

    Exact, and fast on long tracks: a fix can only start a stay if the first fix min_duration_s
    later is still within the radius with no unbridgeable silence in between, a test made for all
    fixes at once, so only those candidates are examined one by one."""
    require_sorted(track)
    n = len(track)
    if n == 0:
        return []
    t, lat, lon = track.time, track.lat, track.lon
    index = np.arange(n)
    # the last fix a stay starting at each fix could reach, before the next unbridgeable silence
    breaks = np.r_[np.flatnonzero(np.diff(t) > max_bridge_s), n - 1]  # the track's end stops any stay
    reach = breaks[np.searchsorted(breaks, index)]
    later = np.searchsorted(t, t + min_duration_s, side="left")
    candidate = later <= reach
    probe = np.minimum(later, n - 1)
    candidate &= np.asarray(haversine(lat, lon, lat[probe], lon[probe])) * 1000 <= radius_m
    starts = np.flatnonzero(candidate)

    found, p = [], 0
    while p < len(starts):
        i = int(starts[p])
        end = _stay_end(lat, lon, i, int(reach[i]), radius_m)
        if t[end] - t[i] >= min_duration_s:
            c_lat, c_lon = mean_position(lat[i : end + 1], lon[i : end + 1])
            found.append(Stay(float(t[i]), float(t[end]), c_lat, c_lon, end - i + 1, i, end))
            p = int(np.searchsorted(starts, end + 1))
        else:
            p += 1
    return found


def _stay_end(lat, lon, i, reach, radius_m):
    """Last fix up to `reach` with every fix after i, up to it, within radius_m of fix i."""
    lo, size = i + 1, _SCAN_CHUNK
    while lo <= reach:
        hi = min(lo + size, reach + 1)
        far = np.flatnonzero(np.asarray(haversine(lat[i], lon[i], lat[lo:hi], lon[lo:hi])) * 1000 > radius_m)
        if len(far):
            return lo + int(far[0]) - 1
        lo, size = hi, size * 2
    return reach


def trips(track, stays):
    """The movement between consecutive stays (as returned by `stays`), one Trip per pair."""
    ordered = sorted(stays, key=lambda s: s.first_index)
    if len(ordered) < 2:
        return []
    legs = step_km(track)
    legs[~in_segment_steps(track)] = 0.0
    along = np.r_[0.0, np.cumsum(legs)]
    t = track.time
    out = []
    for a, b in pairwise(ordered):
        first, last = a.last_index, b.first_index
        distance = float(along[last] - along[first])
        out.append(Trip(float(t[first]), float(t[last]), first, last, last - first + 1, distance, a, b))
    return out
