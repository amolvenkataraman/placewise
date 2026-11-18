"""Entities from ranked candidates: the place (id, name, kind, codes, aliases), its point, box,
radius and (on request) outline, and where it is (city, region, country), looked up for all
results at once and cached.

Context comes from reverse lookup's country and admin1 rules (`context.Where`) on the default
worldview, and from the Geocoder's full reverse lookup when another worldview applies or a city
is wanted (neighbourhoods, postal codes, airports, landmarks)."""

import threading
from collections import OrderedDict

import numpy as np

from placewise.constants import search as const
from placewise.constants._keys import city_key as name_key
from placewise.constants.names import PLACE_KINDS
from placewise.model import BBox, Entity, Outline, Place, Point

from .context import Where

__all__ = ["Contexts", "entity", "level", "light_place", "name_key", "place", "point_entity"]


def level(kind):
    return const.CONTEXT_LEVEL.get(kind, const.CONTEXT_LEVEL_DEFAULT)


class Contexts:
    """(city, region, country, admin1 code) for points, per worldview, with an LRU cache."""

    def __init__(self, geocoder, size=const.REVERSE_CACHE_SIZE):
        self.geocoder = geocoder
        self.size = size
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def get(self, lat, lon, want_city, worldview):
        order = self._order(worldview)
        keys = [(round(a, 5), round(b, 5), c, order) for a, b, c in zip(lat, lon, want_city, strict=True)]
        out = [None] * len(keys)
        with self._lock:
            for i, k in enumerate(keys):
                if k in self._cache:
                    self._cache.move_to_end(k)
                    out[i] = self._cache[k]
        todo = [i for i, v in enumerate(out) if v is None]
        if todo:
            found = self._compute(
                [lat[i] for i in todo], [lon[i] for i in todo], [want_city[i] for i in todo], order
            )
            with self._lock:
                for i, value in zip(todo, found, strict=True):
                    out[i] = value
                    self._cache[keys[i]] = value
                while len(self._cache) > self.size:
                    self._cache.popitem(last=False)
        return out

    def _order(self, worldview):
        order, locked = self.geocoder._order(worldview)
        return tuple(order) + (("locked",) if locked else ())

    def _compute(self, lat, lon, want_city, order):
        lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        out = [None] * len(lat)
        view = [o for o in order if o != "locked"]
        full = [i for i, w in enumerate(want_city) if w or view != ["de_facto"]]
        if full:
            results = self.geocoder._lookup_places(lat[full], lon[full], worldview=view or None)
            for i, r in zip(full, results, strict=True):
                city = r.city or r.locality
                admin1 = r.admin1.codes.get("iso", "").partition("-")[2] if r.admin1 else None
                out[i] = (
                    city.name if city else None,
                    r.admin1.name if r.admin1 else None,
                    r.cc,
                    admin1 or None,
                )
        rest = [i for i, v in enumerate(out) if v is None]
        if rest:
            where = Where(self.geocoder.admin, lat[rest], lon[rest])
            for j, i in enumerate(rest):
                out[i] = (None, where.admin1_name[j], where.country[j], where.admin1[j])
        return out


def place(index, pack, layer, row, kind, context, renames, outlines=False):
    """(Place, Resolved) for one feature; `context` (city, region, country, admin1 code)."""
    resolved = _resolve(index, layer, row, outlines)
    columns = resolved.columns
    codes = {c: str(columns[c]) for c in const.CODE_COLUMNS if columns.get(c) not in (None, "")}
    if context[2]:
        codes["iso2"] = context[2]
    if context[3]:
        codes["admin1"] = context[3]
    aliases = tuple(a for a in str(columns.get("aliases") or "").split("|") if a)
    rename = renames.get(resolved.id)
    name = rename.name if rename is not None else resolved.name
    if rename is not None:
        aliases = (*rename.aliases, resolved.name, *aliases)
    layer_obj = pack[resolved.layer]
    tier = columns.get("tier")
    built = Place(
        id=resolved.id,
        name=name,
        kind=kind,
        point=Point(resolved.lat, resolved.lon),
        bbox=resolved.bbox,
        tier=int(tier) if tier is not None else None,
        codes=codes,
        aliases=tuple(dict.fromkeys(aliases)),
        source=layer_obj.sources[0] if layer_obj.sources else None,
    )
    return built, resolved


def entity(built, resolved, context, score, alternates=(), geometry=False):
    lvl = level(built.kind.value)
    outline = None
    if geometry and resolved.outlines:
        outline = Outline(tuple(ring for o in resolved.outlines for ring in o.rings))
    return Entity(
        place=built,
        point=built.point,
        bbox=resolved.bbox,
        radius_km=max(float(resolved.radius_km), 0.0),
        outline=outline,
        city=context[0] if lvl >= const.CONTEXT_LEVEL_DEFAULT else None,
        region=context[1] if lvl >= 2 else None,
        country=context[2] if lvl >= 0 else None,
        score=round(float(score), 6),
        alternates=tuple(alternates),
    )


def light_place(index, pack, layer, row, kind, lat, lon):
    """A Place without a lookup, for alternates."""
    lyr = pack[index.layers[layer]]
    return Place(
        id=lyr.value("id", row) or f"{pack.name}/{lyr.name}:{row}",
        name=lyr.value("name", row) or "?",
        kind=PLACE_KINDS[kind],
        point=Point(lat, lon),
        source=lyr.sources[0] if lyr.sources else None,
    )


def point_entity(result, lat, lon):
    """The Entity for coordinates typed as text: the point, named by its reverse lookup."""
    city = result.city or result.locality
    label = result.label or f"{lat:.6f}, {lon:.6f}"
    built = Place(
        id=f"{const.GEO_SCHEME}:{lat:.6f},{lon:.6f}",
        name=label,
        kind="custom",
        point=Point(lat, lon),
        codes={"iso2": result.cc} if result.cc else {},
    )
    return Entity(
        place=built,
        point=built.point,
        bbox=BBox(lat, lon, lat, lon),
        radius_km=0.0,
        city=city.name if city else None,
        region=result.admin1.name if result.admin1 else None,
        country=result.cc,
        score=1.0,
    )


def _resolve(index, layer, row, outlines):
    try:
        return index.resolve(layer, row, outlines=outlines)
    except TypeError:  # an index whose resolve always builds the outlines
        return index.resolve(layer, row)
