"""Splitting a track into what the traveller was doing: stays, the trips between them, travel
modes and flights. Track times must be non-decreasing."""

import heapq
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from placewise.constants.tracks import (
    AIRBORNE_MIN_KMH,
    BIKE_MAX_KMH,
    GAP_S,
    JUMP_ANY_KM,
    JUMP_KM,
    JUMP_WITHIN_S,
    MODE_WINDOW_S,
    STAY_MAX_BRIDGE_S,
    STAY_MIN_DURATION_S,
    STAY_RADIUS_M,
    WALK_MAX_KMH,
)
from placewise.geo.distances import haversine
from placewise.model._base import Model

from ._ops import in_segment_steps, mean_position, require_sorted, step_km

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


@dataclass(frozen=True, slots=True)
class ModeRun(Model):
    """A stretch of one travel mode, from fix first_index to fix last_index."""

    mode: str
    start: float
    end: float
    first_index: int
    last_index: int
    distance_km: float


@dataclass(frozen=True, slots=True)
class Flight(Model):
    """kind "airborne": the track recorded the flight; "silent": a jump between two fixes too far
    apart for the time between them to be anything else."""

    start: float
    end: float
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    distance_km: float  # great circle between the end points
    first_index: int
    last_index: int
    kind: str


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


def _chord_kmh(t, lat, lon, a, b):
    """Speed over the straight line from fix a to fix b; NaN where no time passes."""
    dt = t[b] - t[a]
    km = np.asarray(haversine(lat[a], lon[a], lat[b], lon[b]))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(dt > 0, km / dt * 3600.0, np.nan)


def travel_mode(track, window_s=MODE_WINDOW_S):
    """Travel mode of every step (fix k -> k + 1), as a string array of length len(track) - 1:
    "walk" under WALK_MAX_KMH, "bike" up to BIKE_MAX_KMH, "drive" above it, "flight" when over
    AIRBORNE_MIN_KMH both in the window before and the window after the step, "gap" for steps
    across a segment break or longer than GAP_S.

    Speeds are straight-line distance over a window of at least window_s centred on the step, so
    a few metres of GPS jitter between fixes don't register as movement; the median of three
    chords, each dropping one end fix, keeps a single bad fix at the window's edge from swinging
    it. Modes that last less than window_s are then merged into the longer neighbouring mode
    (flights and gaps are left alone), so a car slowing down doesn't flicker through "bike"."""
    require_sorted(track)
    n = len(track)
    if n < 2:
        return np.zeros(0, dtype="<U6")
    t, lat, lon = track.time, track.lat, track.lon
    gap = ~in_segment_steps(track) | (np.diff(t) > GAP_S)
    # runs of fixes joined by classifiable steps; windows never reach outside their run
    run_starts = np.r_[0, np.flatnonzero(gap) + 1]
    run_ends = np.r_[np.flatnonzero(gap), n - 1]
    run_of = np.r_[0, np.cumsum(gap)]
    k = np.arange(n - 1)
    first, last = run_starts[run_of[k]], np.maximum(run_ends[run_of[k]], k + 1)

    mid = (t[:-1] + t[1:]) / 2
    a = np.clip(np.searchsorted(t, mid - window_s / 2, side="right") - 1, first, k)
    b = np.clip(np.searchsorted(t, mid + window_s / 2, side="left"), k + 1, last)
    speed = _chord_kmh(t, lat, lon, a, b)
    trim = b - a >= 3
    if trim.any():
        x, y = a[trim], b[trim]
        three = np.stack(
            [
                _chord_kmh(t, lat, lon, x + 1, y - 1),
                _chord_kmh(t, lat, lon, x + 1, y),
                _chord_kmh(t, lat, lon, x, y - 1),
            ]
        )
        robust = np.median(three, axis=0)
        speed[trim] = np.where(np.isnan(robust), speed[trim], robust)

    back_from = np.clip(np.searchsorted(t, t[1:] - window_s, side="right") - 1, first, k)
    ahead_to = np.clip(np.searchsorted(t, t[:-1] + window_s, side="left"), k + 1, last)
    airborne = (
        (speed > AIRBORNE_MIN_KMH)
        & (_chord_kmh(t, lat, lon, back_from, k + 1) > AIRBORNE_MIN_KMH)
        & (_chord_kmh(t, lat, lon, k, ahead_to) > AIRBORNE_MIN_KMH)
    )
    modes = np.select(
        [gap, airborne, speed < WALK_MAX_KMH, speed <= BIKE_MAX_KMH],
        ["gap", "flight", "walk", "bike"],
        default="drive",
    ).astype("<U6")
    return _merge_short_runs(modes, t, window_s)


def _runs(labels):
    """(first step, last step) of each run of equal labels."""
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    return np.r_[0, change], np.r_[change, len(labels)] - 1


def _merge_short_runs(modes, t, min_s):
    firsts, lasts = _runs(modes)
    count = len(firsts)
    if count < 2:
        return modes
    first, last = firsts.tolist(), lasts.tolist()
    mode = modes[firsts].tolist()
    prev, nxt = list(range(-1, count - 1)), [*range(1, count), -1]
    alive = [True] * count
    fixed = {"flight", "gap"}

    def duration(r):
        return t[last[r] + 1] - t[first[r]]

    heap = [(duration(r), r) for r in range(count) if mode[r] not in fixed]
    heapq.heapify(heap)
    while heap:
        d, r = heapq.heappop(heap)
        if not alive[r] or d != duration(r) or d >= min_s:
            continue
        sides = [s for s in (prev[r], nxt[r]) if s >= 0 and mode[s] not in fixed]
        if not sides:
            continue
        into = max(sides, key=duration)
        far = nxt[r] if into == prev[r] else prev[r]  # the run on r's other side
        first[into], last[into] = min(first[into], first[r]), max(last[into], last[r])
        alive[r] = False
        _unlink(r, prev, nxt)
        if far >= 0 and mode[far] == mode[into]:
            first[into], last[into] = min(first[into], first[far]), max(last[into], last[far])
            alive[far] = False
            _unlink(far, prev, nxt)
        heapq.heappush(heap, (duration(into), into))

    out = modes.copy()
    for r in range(count):
        if alive[r]:
            out[first[r] : last[r] + 1] = mode[r]
    return out


def _unlink(r, prev, nxt):
    p, q = prev[r], nxt[r]
    if p >= 0:
        nxt[p] = q
    if q >= 0:
        prev[q] = p


def mode_runs(track, window_s=MODE_WINDOW_S):
    """`travel_mode` as a list of ModeRun, one per stretch of the same mode."""
    modes = travel_mode(track, window_s)
    if not len(modes):
        return []
    legs = np.r_[0.0, np.cumsum(step_km(track))]
    t = track.time
    firsts, lasts = _runs(modes)
    return [
        ModeRun(str(modes[s]), float(t[s]), float(t[e + 1]), int(s), int(e + 1), float(legs[e + 1] - legs[s]))
        for s, e in zip(firsts, lasts, strict=True)
    ]


def flights(track, window_s=MODE_WINDOW_S):
    """Flights, as a list of Flight: stretches `travel_mode` calls airborne, and silent jumps
    between consecutive fixes (segment breaks included) of over JUMP_KM within JUMP_WITHIN_S or
    over JUMP_ANY_KM at any time. A jump touching an airborne stretch (the phone lost its fix at
    cruise altitude) is part of that flight."""
    require_sorted(track)
    n = len(track)
    if n < 2:
        return []
    t, lat, lon = track.time, track.lat, track.lon
    km, dt = step_km(track), np.diff(t)
    jump = (km > JUMP_ANY_KM) | ((km > JUMP_KM) & (dt <= JUMP_WITHIN_S))
    air = travel_mode(track, window_s) == "flight"
    groups = []  # [first step, last step, airborne]
    for s in np.flatnonzero(air | jump).tolist():
        joins = groups and groups[-1][1] == s - 1 and (air[s] or groups[-1][2])
        if joins:
            groups[-1][1] = s
            groups[-1][2] |= bool(air[s])
        else:
            groups.append([s, s, bool(air[s])])
    out = []
    for s, e, airborne in groups:
        a, b = s, e + 1
        distance = float(haversine(lat[a], lon[a], lat[b], lon[b]))
        kind = "airborne" if airborne else "silent"
        out.append(
            Flight(
                float(t[a]), float(t[b]), *map(float, (lat[a], lon[a], lat[b], lon[b])), distance, a, b, kind
            )
        )
    return out
