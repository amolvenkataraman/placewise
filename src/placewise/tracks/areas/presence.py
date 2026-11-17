"""Days present per country or region: which areas a track was in on each local calendar day,
by one of the rules in placewise.model.presence. Track times must be non-decreasing.
"""

import datetime as dt

import numpy as np

from placewise.constants.tracks import SLEPT_HOUR
from placewise.geo.polygon_index import PolygonIndex
from placewise.model import DayPresence, PresenceDays
from placewise.model.presence import RULES

from .._ops import in_segment_steps, require_sorted

_DAY_S = 86400
_EPOCH = dt.date(1970, 1, 1)


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
