"""One real place found several times (the world pack's GeoNames Toronto, the Canada pack's census
subdivision, division and metro area of the same name; a park as an outline and as a point) becomes
one answer: the best-shaped candidate, with the others listed as its alternates.

Two candidates are the same place when they share a name (the key they matched or their own
name), their kinds can describe one place (both settlements of some kind, else the same kind), and
they overlap: one's point lies inside the other's outline (a park's point within DEDUPE_PARK_KM of
its outline's box: Wikidata's park coordinates are rough), or both are points within
DEDUPE_POINT_KM of each other.
"""

import math

from placewise.constants import search as const
from placewise.constants.earth import MEAN_RADIUS_KM


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

    items[i]: (keys, kind, lat, lon, polygon, detailed[, id]): `keys` the set of name keys it goes by;
    rows of one feature stored in parts ("pad-us:x", "pad-us:x#2") always merge;
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
    if family(kind_i) != family(kind_j) or not (keys_i & keys_j):
        return False
    stem_i, stem_j = _stem(items[i]), _stem(items[j])
    return (stem_i is not None and stem_i == stem_j) or _overlap(i, j, items, contains)


def _stem(item):
    """The id without a part suffix ("pad-us:x#2" -> "pad-us:x"), or None."""
    ident = item[6] if len(item) > 6 else None
    return ident.partition("#")[0] if ident else None


def _overlap(i, j, items, contains):
    lat_i, lon_i, poly_i = items[i][2:5]
    lat_j, lon_j, poly_j = items[j][2:5]
    if poly_j and contains(j, lat_i, lon_i):
        return True
    if poly_i and contains(i, lat_j, lon_j):
        return True
    if poly_i or poly_j:
        return False
    km = _km(lat_i, lon_i, lat_j, lon_j)
    return math.isfinite(km) and km <= const.DEDUPE_POINT_KM


def _km(lat1, lon1, lat2, lon2):
    """Haversine for two scalar points (plain floats are far cheaper than numpy here)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * MEAN_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def in_box(box, lat, lon):
    """Whether a point lies in a (south, west, north, east) box (west > east: across 180°)."""
    s, w, n, e = box
    return s <= lat <= n and (w <= lon <= e if w <= e else (lon >= w or lon <= e))


def park_box(s, w, n, e):
    """A park outline's box widened by DEDUPE_PARK_KM (longitude degrees shrink with latitude)."""
    dlat = math.degrees(const.DEDUPE_PARK_KM / MEAN_RADIUS_KM)
    dlon = dlat / max(math.cos(math.radians(max(abs(s), abs(n)))), 0.01)
    return s - dlat, w - dlon, n + dlat, e + dlon
