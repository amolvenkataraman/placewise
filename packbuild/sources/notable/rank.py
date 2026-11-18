"""Fame, duplicates and spatial quotas for the notable places.

Fame (0..1) is a percentile within the place's kind, so stations aren't drowned by cathedrals:

1. raw = log10(1 + QRank page views) + log10(1 + sitelinks) (log scale damps news spikes);
2. p_kind = the share of the kind's places with raw at or below this one's;
3. p_local = the same within (kind, country), for groups of at least MIN_GROUP places (else
   p_kind), so a country less read on Wikipedia (India) keeps its best-known places high;
4. fame = (p_kind + p_local) / 2.

Duplicates: places with the same name key (duplicate_key) within DUPLICATE_KM are one place
(Wikidata often has a station and its building, a subway station beside the railway station, or a
tower and its structure): the most famous stays, the others' names and aliases join it.

Floor: a place needs MIN_VIEWS page views a year (MIN_VIEWS_FOCUS in the focus countries:
India, the US, Canada) to be kept at all.

Quotas: in each cell of an equal-area grid (CELL_KM square) only the QUOTA most famous places of a
kind are kept (QUOTA_FOCUS in the focus countries), so dense cities don't
take the whole budget; places at or above FAME_FLOOR and kinds in EXEMPT are always kept.

The budget (the pack at most 40 MB, names index included) set these: 2026.11 has 885k candidate
items, 218k with 1,000+ views a year; the floor and quotas keep about 180k.
"""

import math
import re

import numpy as np

from placewise.constants._keys import city_key
from placewise.geo import haversine

MIN_GROUP = 20
DUPLICATE_KM = 0.3
CELL_KM = 16.0
MIN_VIEWS = 1000
MIN_VIEWS_FOCUS = 200
QUOTA = 5
QUOTA_FOCUS = 12
FOCUS = frozenset({"IN", "US", "CA"})
FAME_FLOOR = 0.98
EXEMPT = frozenset({"university", "campus", "airport"})
_KM_PER_DEG = 111.195
_STATION = re.compile(r" (?:(?:railway|train|metro|subway|underground|bus|rail) )?station$")


def popular(views, countries, min_views=None, min_views_focus=None):
    """Boolean mask of the places with enough page views (default floors: MIN_VIEWS, and
    MIN_VIEWS_FOCUS in the FOCUS countries)."""
    views = np.asarray(views, dtype=np.float64)
    focused = np.array([c in FOCUS for c in countries], dtype=bool)
    low = MIN_VIEWS_FOCUS if min_views_focus is None else min_views_focus
    return views >= np.where(focused, low, MIN_VIEWS if min_views is None else min_views)


def raw_fame(views, sitelinks):
    return np.log10(1.0 + np.asarray(views, dtype=np.float64)) + np.log10(
        1.0 + np.asarray(sitelinks, dtype=np.float64)
    )


def percentile(values):
    """For each value, the share of values at or below it (1.0 for the largest)."""
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return values
    ordered = np.sort(values)
    return np.searchsorted(ordered, values, side="right") / len(values)


def fame(raw, kinds, countries, min_group=MIN_GROUP):
    """fame per place (see the module docstring); `countries` is "" where unknown."""
    raw = np.asarray(raw, dtype=np.float64)
    kinds, countries = np.asarray(kinds, dtype=object), np.asarray(countries, dtype=object)
    p_kind, p_local = np.zeros(len(raw)), np.zeros(len(raw))
    for kind in set(kinds.tolist()):
        in_kind = np.flatnonzero(kinds == kind)
        p_kind[in_kind] = percentile(raw[in_kind])
        p_local[in_kind] = p_kind[in_kind]
        for country in set(countries[in_kind].tolist()):
            group = in_kind[countries[in_kind] == country]
            if country and len(group) >= min_group:
                p_local[group] = percentile(raw[group])
    return (p_kind + p_local) / 2


def duplicate_key(name):
    """The name key duplicates share: a leading "the" and a trailing "(railway) station" dropped, so
    the subway's "Union" and the railway's "Union Station" are one place."""
    k = city_key(name)
    k = k[4:] if k.startswith("the ") else k
    return _STATION.sub("", k) or k


def duplicates(names, lat, lon, fame_values, km=DUPLICATE_KM):
    """{dropped index: kept index} for places sharing a name key within `km` of a more famous one
    (ties: the lower index stays)."""
    groups = {}
    for i, name in enumerate(names):
        groups.setdefault(duplicate_key(name), []).append(i)
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    fame_values = np.asarray(fame_values, dtype=np.float64)
    dropped = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda i: (-fame_values[i], i))
        kept = [members[0]]
        for i in members[1:]:
            d = haversine(lat[i], lon[i], lat[kept], lon[kept])
            near = np.flatnonzero(np.atleast_1d(d) <= km)
            if len(near):
                dropped[i] = kept[int(near[0])]
            else:
                kept.append(i)
    return dropped


def cells(lat, lon, cell_km=CELL_KM):
    """An equal-area grid cell id per point: rows cell_km tall, each cut into as many columns as
    fit cell_km wide at its middle latitude."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    dlat = cell_km / _KM_PER_DEG
    n_rows = math.ceil(180 / dlat)
    row = np.clip(np.floor((lat + 90) / dlat).astype(np.int64), 0, n_rows - 1)
    middle = np.radians(-90 + (row + 0.5) * dlat)
    n_cols = np.maximum(1, np.floor(360 * np.cos(middle) / dlat)).astype(np.int64)
    col = np.clip(np.floor((lon + 180) / 360 * n_cols).astype(np.int64), 0, n_cols - 1)
    max_cols = math.ceil(360 / dlat)
    return row * max_cols + col


def quota_keep(lat, lon, kinds, countries, fame_values, quota=QUOTA, quota_focus=QUOTA_FOCUS,
               floor=FAME_FLOOR, exempt=EXEMPT, focus=FOCUS, cell_km=CELL_KM):  # fmt: skip
    """Boolean mask of the places kept by the spatial quotas (see the module docstring)."""
    fame_values = np.asarray(fame_values, dtype=np.float64)
    kinds, countries = np.asarray(kinds, dtype=object), np.asarray(countries, dtype=object)
    cell = cells(lat, lon, cell_km)
    keep = (fame_values >= floor) | np.isin(kinds, list(exempt))
    order = np.lexsort((np.arange(len(fame_values)), -fame_values))  # most famous first
    taken = {}
    for i in order.tolist():
        if keep[i]:
            continue
        slot = (int(cell[i]), kinds[i])
        limit = quota_focus if countries[i] in focus else quota
        if taken.get(slot, 0) < limit:
            taken[slot] = taken.get(slot, 0) + 1
            keep[i] = True
    return keep
