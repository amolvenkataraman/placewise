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


def polygon(layer, lat, lon, snap_km=const.SHORE_KM):
    """(feature or -1, rule) per point: the containing feature ("polygon"), else the one whose
    boundary is nearest within snap_km ("nearest"), for shapes clipped to the shoreline."""
    rows = np.atleast_1d(layer.query(lat, lon)).astype(np.int64)
    rule = np.where(rows >= 0, lookup_const.POLYGON, "").astype(object)
    miss = np.flatnonzero(rows < 0)
    if len(miss) and snap_km:
        q, f, d = layer.near_boundary(lat[miss], lon[miss], snap_km)
        best = best_per_query(q, d, len(miss))
        hit = best >= 0
        rows[miss[hit]] = f[best[hit]]
        rule[miss[hit]] = lookup_const.NEAREST
    return rows, rule


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
    names = cities.layers.column(lookup_const.CITIES, "name")
    for i in np.flatnonzero(ok.any(axis=1)).tolist():
        for j in np.flatnonzero(ok[i]).tolist():
            if skip is None or not skip(i, names[safe[i, j]]):
                out[i] = safe[i, j]
                break
    return out


def regions(layers, key, lat, lon):
    """Per point, a tuple of the curated regions containing it, smallest (by bounding box) first."""
    layer = layers.layer(key)
    point, feature = layer.query_every(lat, lon)
    out = np.full(len(lat), None, dtype=object)
    if not len(point):
        return out
    bbox = np.array([_box(layer.bbox(f)) for f in range(layer.count)], dtype=float).reshape(-1, 4)
    width = np.where(bbox[:, 3] >= bbox[:, 1], bbox[:, 3] - bbox[:, 1], bbox[:, 3] - bbox[:, 1] + 360)
    area = (bbox[:, 2] - bbox[:, 0]) * width * np.cos(np.radians((bbox[:, 0] + bbox[:, 2]) / 2))
    order = np.lexsort((area[feature], point))
    groups = {}
    for p, f in zip(point[order].tolist(), feature[order].tolist(), strict=True):
        groups.setdefault(p, []).append(layers.place(key, f))
    for p, found in groups.items():
        out[p] = tuple(found)
    return out


def _box(b):
    return b.south, b.west, b.north, b.east


def set_regions(out, layers, key, lat, lon):
    """Fill out.regions from a curated regions layer."""
    found = regions(layers, key, lat, lon)
    for i in np.flatnonzero(found != None).tolist():  # noqa: E711 - element-wise
        out.regions[i] = found[i]
        out.sources[i]["regions"] = f"{key}:{lookup_const.POLYGON}"


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
