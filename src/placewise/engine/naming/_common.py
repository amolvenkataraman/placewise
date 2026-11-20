"""What the per-country naming rules share: polygon lookups that reach the shore, GeoNames places
inside a boundary, curated regions, and turning rows into per-point Places."""

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import naming as const
from placewise.model import Place, PlaceKind, Point

from .._index import best_per_query
from .._layers import codes, source_of
from . import rules


class Named:
    """The naming rules' answer for m points: object arrays of Places per field, regions tuples
    and one sources dict per point."""

    FIELDS = ("sublocality", "locality", "city", "borough", "admin2", "postal")

    def __init__(self, m, layers):
        self.m, self.layers = m, layers
        self.every = np.arange(m)
        for field in self.FIELDS:
            setattr(self, field, np.full(m, None, dtype=object))
        self.regions = np.full(m, None, dtype=object)
        self.sources = [{} for _ in range(m)]
        # {field: km} where a rule measured how far a fallback place is (Result.matches); None: none
        self.km = [None] * m

    def measured(self, field, pts, km):
        """Points `pts` are `km` from their `field` place's outline (a fallback's distance)."""
        for i, d in zip(np.asarray(pts).tolist(), np.asarray(km, dtype=np.float64).tolist(), strict=True):
            if self.km[i] is None:
                self.km[i] = {}
            self.km[i][field] = d

    def set(self, field, pts, places, source):
        """Points `pts` (indexes into the m) get `places` (an object array) for `field`; the
        sources entry is set where the place isn't None. `source` is one string or one per point."""
        getattr(self, field)[pts] = places
        many = not isinstance(source, str)
        for j, (i, p) in enumerate(zip(np.asarray(pts).tolist(), places.tolist(), strict=True)):
            if p is not None:
                self.sources[i][field] = source[j] if many else source

    def put(self, field, pts, key, rows, rule, kind=None):
        """Points `pts` get the Places of layer `key`'s `rows` (-1: none), with source "key:rule"
        (`rule` one string or an array, one per point)."""
        name = self.layers.source
        source = (
            name(key, rule) if isinstance(rule, str) else [name(key, r) for r in np.asarray(rule).tolist()]
        )
        self.set(field, pts, places_for(self.layers, key, rows, kind), source)

    def sublocality_inside(self, cities, key, feature, local, local_km):
        """The sublocality: the nearest GeoNames place within SUBLOCALITY_KM in the point's own
        `feature` of layer `key`, not named like its locality, city or borough. Returns the city
        rows found (-1: none)."""

        def skip(i, name):
            names = (self.locality[i], self.city[i], self.borough[i])
            return any(rules.same_name(name, p.name) for p in names if p is not None)

        found = geonames_inside(
            cities,
            key,
            feature,
            local,
            local_km,
            const.SUBLOCALITY_KM,
            const.SUBLOCALITY_EXCLUDED_FEATURE_CODES,
            skip,
        )
        has = np.flatnonzero(found >= 0)
        self.put("sublocality", has, lookup_const.CITIES, found[has], const.INSIDE, PlaceKind.SUBLOCALITY)
        return found


def tz_layers(layers, pack, finest, coarser):
    """The keys of the layers carrying the time-zone column (placewise.engine._timezones), finest
    first: `finest` (a key) and the `coarser` layers of `pack` (names) that it lies in; [] when the
    finest units carry no zone (packs built before the column)."""
    if lookup_const.TZ_FIELD not in layers.layer(finest).fields:
        return []
    found = [layers.add(pack, name) for name in coarser if name in pack]
    return [finest, *(k for k in found if lookup_const.TZ_FIELD in layers.layer(k).fields)]


def inside_rows(rows, rule):
    """`rows` (features per point, as `polygon` gives them) where the point is inside, else -1."""
    return np.where(rule == lookup_const.POLYGON, rows, -1)


def polygon(layer, lat, lon, snap_km=const.SHORE_KM):
    """(feature or -1, rule) per point: the containing feature ("polygon"), else the one whose
    boundary is nearest within snap_km ("nearest"), for shapes clipped to the shoreline."""
    rows = np.atleast_1d(layer.query(lat, lon)).astype(np.int64)
    rule = np.where(rows >= 0, lookup_const.POLYGON, "").astype(object)
    miss = np.flatnonzero(rows < 0)
    if len(miss) and snap_km:
        q, f, d = _near_features(layer, lat[miss], lon[miss], snap_km)
        best = best_per_query(q, d, len(miss))
        hit = best >= 0
        rows[miss[hit]] = f[best[hit]]
        rule[miss[hit]] = lookup_const.NEAREST
    return rows, rule


_PAIRS_PER_BLOCK = 4_000_000


def near_bbox(boxes, rows, lat, lon, km):
    """Per point, whether it lies within km (roughly, never too strict) of the bounding box of its
    feature `rows` (False where the row is -1): the cheap test before an exact distance."""
    ok = rows >= 0
    b = boxes[np.maximum(rows, 0)]
    dlat = np.asarray(km) / 110.0
    dlon = dlat / np.maximum(np.cos(np.radians(np.minimum(np.abs(lat) + dlat, 89.9))), 0.01)
    in_lat = (lat >= b[:, 0] - dlat) & (lat <= b[:, 2] + dlat)
    wraps = b[:, 1] > b[:, 3]
    in_lon = np.where(
        wraps,
        (lon >= b[:, 1] - dlon) | (lon <= b[:, 3] + dlon),
        (lon >= b[:, 1] - dlon) & (lon <= b[:, 3] + dlon),
    )
    return ok & in_lat & in_lon


def _near_features(layer, lat, lon, km):
    """(point, feature, km) for features whose boundary is within km of each point. Few points
    miss every feature (water by the shore), so this tests their bounding boxes and then measures
    the few candidates exactly, instead of indexing every edge of the layer
    (PolygonLayer.near_boundary), which costs seconds for big layers."""
    boxes = layer.bboxes()
    dlat = km / 111.0
    dlon = dlat / np.maximum(np.cos(np.radians(np.abs(lat))), 0.01)
    q_all, f_all = [], []
    step = max(1, _PAIRS_PER_BLOCK // max(len(boxes), 1))
    for s in range(0, len(lat), step):
        y, x, w = lat[s : s + step, None], lon[s : s + step, None], dlon[s : s + step, None]
        south, west, north, east = (boxes[None, :, k] for k in range(4))
        near_lat = (y >= south - dlat) & (y <= north + dlat)
        wraps = west > east  # crosses the antimeridian
        near_lon = np.where(wraps, (x >= west - w) | (x <= east + w), (x >= west - w) & (x <= east + w))
        q, f = np.nonzero(near_lat & near_lon)
        q_all.append(q + s)
        f_all.append(f)
    q, f = np.concatenate(q_all), np.concatenate(f_all)
    d = np.atleast_1d(layer.nearest_edge_km(lat[q], lon[q], f))  # each to its own feature, at once
    keep = d <= km
    return q[keep], f[keep], d[keep]


def places_for(layers, key, rows, kind=None):
    """Object array of the Places for layer rows (None where -1), each made once; `kind`
    re-kinds them (a census place as a sublocality)."""
    rows = np.asarray(rows, dtype=np.int64)
    out = np.full(len(rows), None, dtype=object)
    if not len(rows):
        return out
    unique, inverse = np.unique(rows, return_inverse=True)
    made = np.full(len(unique), None, dtype=object)
    for j, r in enumerate(unique.tolist()):
        if r >= 0:
            p = layers.place(key, r)
            made[j] = p if kind is None or p.kind == kind else rekind(layers, key, r, kind)
    out[:] = made[inverse.ravel()]
    return out


def rekind(layers, key, row, kind):
    """The layer row's Place with another kind, made once."""
    cache = layers.cache(f"{key}#{kind.value}")
    if row not in cache:
        p = layers.place(key, row)
        cache[row] = Place(p.id, p.name, kind, point=p.point, bbox=p.bbox, codes=p.codes, source=p.source)
    return cache[row]


def geonames_inside(cities, key, feature, local, local_km, max_km, excluded_codes, skip=None):
    """Per point, the nearest GeoNames candidate (local, local_km: (m, k), nearest first) within
    max_km whose point lies in the point's own `feature` of layer `key`, whose feature code isn't
    excluded and, with skip(i, name) -> bool, whose name isn't skipped; -1 where none."""
    m = len(feature)
    out = np.full(m, -1, dtype=np.int64)
    if not m:
        return out
    safe = np.maximum(local, 0)
    ok = (local >= 0) & (local_km <= max_km) & (feature[:, None] >= 0)
    ok &= ~np.isin(cities.table["feature_code"][safe], list(excluded_codes))
    if ok.any():
        inside = np.full(local.shape, -1, dtype=np.int64)
        inside[ok] = cities.inside(key, safe[ok])
        ok &= inside == feature[:, None]
    for i in np.flatnonzero(ok.any(axis=1)).tolist():
        for j in np.flatnonzero(ok[i]).tolist():
            if skip is None or not skip(i, cities.layers.value(lookup_const.CITIES, "name", int(safe[i, j]))):
                out[i] = safe[i, j]
                break
    return out


def set_regions(out, layers, lat, lon, curated=None, statistical=()):
    """Fill out.regions with every region containing each point, smallest first: the curated
    `regions` layer's (key or None, which may overlap) and the statistical areas, given as
    (key, feature row per point) pairs (CBSA, CSA, CMA). The smallest one's layer is the source."""
    found = [[] for _ in range(out.m)]
    if curated is not None:
        point, feature = layers.layer(curated).query_every(lat, lon)
        for p, f in zip(point.tolist(), feature.tolist(), strict=True):
            found[p].append((curated, f))
    for key, rows in statistical:
        for i in np.flatnonzero(rows >= 0).tolist():
            found[i].append((key, int(rows[i])))
    for i, items in enumerate(found):
        if items:
            items.sort(key=lambda kr: region_area(layers, *kr))
            out.regions[i] = tuple(layers.place(k, r) for k, r in items)
            out.sources[i]["regions"] = layers.source(items[0][0], lookup_const.POLYGON)


def region_area(layers, key, row):
    """A region's area (km2): the layer's area_km2 column if it has one, else its outlines',
    computed once."""
    cache = layers.cache(f"{key}#area")
    if row not in cache:
        layer = layers.layer(key)
        value = layer.value("area_km2", row) if "area_km2" in layer.fields else None
        cache[row] = value if value is not None else sum(o.area_km2 for o in layer.feature(row).outlines)
    return cache[row]


def region_place(get, layer, i):
    return Place(
        get("id"), get("name") or get("id"), PlaceKind.REGION, bbox=layer.bbox(i),
        codes=codes(get, "kind", "type", "country"), source=source_of(layer),
    )  # fmt: skip


def area_maker(kind, *fields, point=("intpt_lat", "intpt_lon"), name="name"):
    """A Place maker for a polygon layer: `kind`, its `name` field (falling back to the id), the
    given code fields and the internal point if the layer has one."""

    def make(get, layer, i):
        at = None
        if point[0] in layer.fields:
            lat, lon = layer.value(point[0], i), layer.value(point[1], i)
            at = Point(lat, lon) if lat is not None and lon is not None else None
        found = codes(get, *fields)
        return Place(get("id"), get(name) or get("id"), kind, point=at, bbox=layer.bbox(i), codes=found,
                     source=source_of(layer))  # fmt: skip

    return make


def population(layer):
    """The layer's population column as float, NaN for nulls and when it has none."""
    if "population" not in layer.fields:
        return np.full(layer.count, np.nan)
    values = np.asarray(layer.column("population"), dtype=np.float64)
    null = layer.nulls.get("population")
    return np.where(values == null, np.nan, values) if null is not None else values


def skip_near(cities, key, a, pts, locality, city):
    """GeoNames' notable cities whose point lies in the locality's or city's own feature of layer
    `key` are that place, not "near" it (New York City in New York): dropped from a["notable"]."""
    notable = a["notable"][pts]
    ok = notable >= 0
    if ok.any():
        inside = np.full(notable.shape, -1, dtype=np.int64)
        inside[ok] = cities.inside(key, notable[ok])
        same = ok & (inside >= 0) & ((inside == locality[:, None]) | (inside == city[:, None]))
        notable[same] = -1
        a["notable"][pts] = notable
