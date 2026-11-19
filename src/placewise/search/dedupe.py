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

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import search as const
from placewise.constants._keys import city_key
from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.names import PLACE_KINDS


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


def groups(packs, pool, order):
    """The candidates `order` lists (best first) merged into groups of one place each, best first,
    each group's best candidate first (merge), from their names, kinds, points and outlines."""
    items = {}
    for i in order:
        pack = packs[int(pool.pack[i])]
        index = pack.names
        layer = int(pool.layer[i])
        lyr = pack[index.layers[layer]]
        keys = {index.key(int(pool.entry[i])), city_key(lyr.value("name", int(pool.row[i])))}
        polygon = index.layer_kind(layer) == "polygon"
        items[int(i)] = (
            frozenset(keys),
            PLACE_KINDS[int(pool.kind[i])],
            float(pool.lat[i]),
            float(pool.lon[i]),
            polygon,
            polygon and pack.name != lookup_const.DEFAULT_PACK,
            lyr.value("id", int(pool.row[i])),
        )

    inside = _inside_pairs(packs, pool, items)
    return merge([int(i) for i in order], items, lambda i, lat, lon: (i, lat, lon) in inside)


def _inside_pairs(packs, pool, items):
    """{(i, lat, lon)}: candidate i's outline holds that point of another candidate it could be
    merged with (for a park, the point is within DEDUPE_PARK_KM of the outline's box); every
    such test of one layer in one vectorised call."""
    asks = {}  # (pack, layer) -> ([row], [lat], [lon], [i])
    found = set()
    for i, (keys_i, kind_i, *_rest) in items.items():
        if not items[i][4]:
            continue
        lyr = _layer(packs, pool, i)
        s, w, n, e = lyr.bboxes()[int(pool.row[i])].tolist()
        park = park_box(s, w, n, e) if kind_i == const.PARK_KIND else None
        for j, (keys_j, kind_j, lat, lon, *_more) in items.items():
            if j == i or family(kind_i) != family(kind_j) or not (keys_i & keys_j):
                continue
            if park is not None and not items[j][4] and in_box(park, lat, lon):
                found.add((i, lat, lon))
            elif in_box((s, w, n, e), lat, lon):
                ask = asks.setdefault((int(pool.pack[i]), int(pool.layer[i])), ([], [], [], []))
                for part, value in zip(ask, (int(pool.row[i]), lat, lon, i), strict=True):
                    part.append(value)
    for (pack, layer), (rows, lats, lons, owners) in asks.items():
        lyr = packs[pack][packs[pack].names.layers[layer]]
        hit = np.atleast_1d(lyr.contains(np.array(lats), np.array(lons), np.array(rows)))
        found.update((owners[k], lats[k], lons[k]) for k in np.flatnonzero(hit))
    return found


def _layer(packs, pool, i):
    pack = packs[int(pool.pack[i])]
    return pack[pack.names.layers[int(pool.layer[i])]]
