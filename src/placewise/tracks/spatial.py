"""A track against places: time inside an area, crossings between areas, the closest pass to a
point, the track's extent and days present per country or region.

Where a step between two fixes crosses an area's edge, the crossing is located by bisection along
the great circle between them and its time interpolated at constant speed. Steps across a segment
break are never interpolated. Track times must be non-decreasing.
"""

import datetime as dt
from typing import NamedTuple

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.tracks import SLEPT_HOUR
from placewise.geo.distances import haversine
from placewise.geo.lines import _nearest_on_arcs
from placewise.geo.polygon_index import PolygonIndex
from placewise.model import BBox, DayPresence, PresenceDays
from placewise.model.presence import RULES

from ._ops import bisect_change, in_segment_steps, require_sorted, step_km, unit_vectors

_DAY_S = 86400
_EPOCH = dt.date(1970, 1, 1)


class Crossing(NamedTuple):
    time: float
    from_index: int  # index into the features, -1 for none
    to_index: int


class ClosestPass(NamedTuple):
    time: float
    distance_km: float
    index: int  # the fix at or just before the closest point


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


def presence_days(track, features, codes, tz_offsets_s=None, rule="any_part", by="country"):
    """Days present per code as PresenceDays. `codes[i]` is the code (an ISO country or admin1
    code) of `features[i]`; several features may share one. Days are local calendar days:
    `tz_offsets_s` gives each fix's UTC offset in seconds (an array, or one number for all);
    without it days are UTC days.

    rule "any_part": every code with a fix that day. "slept": the code of the last fix before
    SLEPT_HOUR (03:00) local the next morning, counted for the evening's date. "majority": the code
    with the most time that day, each fix standing for half the step before and after it within
    its segment (fixes outside every feature compete for nothing).

    Each counted day carries the first and last fix of the stretch it was judged on (the local day,
    or 03:00 to 03:00 for "slept") as timezone-aware datetimes in the fix's own offset. Days with no
    fix inside any feature are left out."""
    if rule not in RULES:
        raise ValueError(f"rule must be one of {sorted(RULES)}, not {rule!r}")
    features = features.features if isinstance(features, PolygonIndex) else list(features)
    codes = list(codes)
    if len(codes) != len(features):
        raise ValueError(f"need one code per feature: {len(features)} features, {len(codes)} codes")
    require_sorted(track)
    n = len(track)
    if n == 0:
        return PresenceDays(by, rule, ())
    offsets = np.zeros(n) if tz_offsets_s is None else np.asarray(tz_offsets_s, dtype=np.float64)
    if offsets.ndim == 0:
        offsets = np.full(n, float(offsets))
    if offsets.shape != (n,):
        raise ValueError(f"tz_offsets_s needs one offset per fix ({n}), got shape {offsets.shape}")

    unique_codes, code_of_feature = np.unique(np.asarray(codes, dtype=str), return_inverse=True)
    names = [str(c) for c in unique_codes]
    hit = np.atleast_1d(PolygonIndex(features).query(track.lat, track.lon))
    code = np.where(hit >= 0, code_of_feature[np.maximum(hit, 0)], -1)

    local = track.time + offsets
    if rule == "slept":
        local = local - SLEPT_HOUR * 3600
    day = np.floor(local / _DAY_S).astype(np.int64)
    # group fixes by day; a stable sort keeps each day's fixes in track (time) order
    order = np.argsort(day, kind="stable")
    bounds = np.r_[0, np.flatnonzero(np.diff(day[order])) + 1, n]
    group = np.empty(n, dtype=np.int64)
    group[order] = np.repeat(np.arange(len(bounds) - 1), np.diff(bounds))

    if rule == "any_part":
        coded = code >= 0
        pairs = np.unique(group[coded] * len(names) + code[coded])
        chosen = {}
        for g, c in zip((pairs // len(names)).tolist(), (pairs % len(names)).tolist(), strict=True):
            chosen.setdefault(g, []).append(names[c])
    elif rule == "slept":
        last = order[bounds[1:] - 1]
        chosen = {g: [names[code[i]]] for g, i in enumerate(last.tolist()) if code[i] >= 0}
    else:
        chosen = _majority(track, group, code, names)

    days = []
    for g, day_codes in sorted(chosen.items()):
        first, last = int(order[bounds[g]]), int(order[bounds[g + 1] - 1])
        days.append(
            DayPresence(
                date=_EPOCH + dt.timedelta(days=int(day[first])),
                codes=tuple(sorted(day_codes)),
                first_fix=_local_datetime(track.time[first], offsets[first]),
                last_fix=_local_datetime(track.time[last], offsets[last]),
            )
        )
    return PresenceDays(by, rule, tuple(days))


def _majority(track, group, code, names):
    steps = np.where(in_segment_steps(track), np.diff(track.time), 0.0)
    weight = np.r_[steps, 0.0] / 2 + np.r_[0.0, steps] / 2
    coded = code >= 0
    key = group[coded] * len(names) + code[coded]
    # a tiny per-fix bonus breaks ties (and decides days of lone fixes) by the number of fixes
    score = np.bincount(key, weights=weight[coded] + 1e-6)
    keys = np.flatnonzero(score > 0)
    best = {}
    for k in keys.tolist():
        g = k // len(names)
        if g not in best or score[k] > score[best[g]]:
            best[g] = k
    return {g: [names[k % len(names)]] for g, k in best.items()}


def _local_datetime(t, offset_s):
    tz = dt.timezone.utc if offset_s == 0 else dt.timezone(dt.timedelta(seconds=float(offset_s)))
    return dt.datetime.fromtimestamp(float(t), tz=tz)
