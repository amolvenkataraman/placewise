"""One real place found several times (the world pack's GeoNames Toronto, the Canada pack's census
subdivision, division and metro area of the same name; a park as an outline and as a point) becomes
one answer: the best-shaped candidate, with the others listed as its alternates.

Two candidates are the same place when they share a name (the key they matched or their own
name), their kinds can describe one place (both settlements of some kind, else the same kind), and
they overlap: one's point lies inside the other's outline, or both are points within
DEDUPE_POINT_KM of each other.
"""

import math

from placewise.constants import search as const
from placewise.geo.distances import haversine


def family(kind):
    """Kinds of one family may describe the same place: every settlement kind shares one."""
    return "settlement" if kind in const.SETTLEMENT_PREFERENCE else kind


def preference(kind, polygon, detailed):
    """How good a representative a candidate makes, higher first: settlements by kind (the city
    over its metro area), then an outline over a point, then a country pack's outline over the
    world pack's."""
    return (const.SETTLEMENT_PREFERENCE.get(kind, 0), bool(polygon), bool(detailed))


def merge(order, items, contains):
    """Groups of candidate indexes, in `order` (best score first), representative first.

    items[i]: (keys, kind, lat, lon, polygon, detailed): `keys` the set of name keys it goes by;
    contains(i, lat, lon) -> whether candidate i's outline holds the point (only asked for
    polygons)."""
    groups = []
    for i in order:
        for group in groups:
            if any(_same(i, j, items, contains) for j in group):
                group.append(i)
                break
        else:
            groups.append([i])
    out = []
    for group in groups:
        best = max(group, key=lambda m: (preference(items[m][1], items[m][4], items[m][5]), -group.index(m)))
        out.append([best, *(m for m in group if m != best)])
    return out


def _same(i, j, items, contains):
    keys_i, kind_i = items[i][:2]
    keys_j, kind_j = items[j][:2]
    return family(kind_i) == family(kind_j) and bool(keys_i & keys_j) and _overlap(i, j, items, contains)


def _overlap(i, j, items, contains):
    _, _, lat_i, lon_i, poly_i, _ = items[i]
    _, _, lat_j, lon_j, poly_j, _ = items[j]
    if poly_j and contains(j, lat_i, lon_i):
        return True
    if poly_i and contains(i, lat_j, lon_j):
        return True
    if poly_i or poly_j:
        return False
    km = float(haversine(lat_i, lon_i, lat_j, lon_j))
    return math.isfinite(km) and km <= const.DEDUPE_POINT_KM
