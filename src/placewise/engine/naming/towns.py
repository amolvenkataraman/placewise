"""Town and city outlines where no country pack names places: the optional world-towns pack.

Its `towns` layer holds GHS-SMOD urban centres and towns (packbuild.towns), each named after a
GeoNames place of the world pack's `cities` (its `geonames` column). A point inside one, in the
outline's own country (as the worldview reports it) and outside the countries whose packs name
places (constants.towns.LEFT_OUT, and any point a country pack's rules answered), is named from it:

- locality: the city score's place (placewise.engine._cities) when that place lies in the same
  outline (a suburb's own name: Puteaux in Paris' outline), else the outline's place;
- city: the outline's place, unless the locality is a place in its own right that doesn't roll up
  into it (naming.rules.rolls_up: 100,000+ people, or not ten times smaller: Yokohama stays
  Yokohama inside Tokyo's outline).

A field the outline names has the source "world-towns/towns:polygon" (Result.matches: within);
the others keep the city score's. Points outside every outline keep the city score's answer.
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.constants import towns as towns_const

from .rules import rolls_up


class Towns:
    """The world-towns layer of a set of packs. Falsy when no pack has it."""

    def __init__(self, packs, layers, admin, cities):
        self.layers, self.admin, self.cities = layers, admin, cities
        self.key = None
        pack = next((p for p in packs if towns_const.LAYER in p.layers and p.name == towns_const.PACK), None)
        if pack is None or cities is None or admin.worldviews is None:
            return
        layer = pack.layers[towns_const.LAYER]
        if layer.kind != "polygon" or not len(layer):
            return
        self.key = layers.add(pack, towns_const.LAYER)
        self.layer = layer
        self.country = np.asarray(layer.column("country"), dtype=object)
        row_of = {pid: i for i, pid in enumerate(cities.layer.column("id").tolist())}
        self.place = np.array([row_of.get(g, -1) for g in layer.column("geonames").tolist()], dtype=np.int64)
        codes = admin.worldviews.code
        self.codes = np.array([*codes, ""], dtype=object)

    def __bool__(self):
        return self.key is not None

    @property
    def source(self):
        return self.layers.source(self.key, const.POLYGON)

    def answer(self, a, lat, lon, work):
        """Fill a["town"] (the outline, -1 for none), a["town_place"] (its city row) and
        a["town_city"], a["town_locality"] (the city rows the fields name) for each point."""
        n = len(lat)
        for name in ("town", "town_place", "town_city", "town_locality"):
            a[name] = np.full(n, -1, dtype=np.int64)
        view = a["view"]
        code = self.codes[np.where(view >= 0, view, len(self.codes) - 1)]
        todo = (a["cidx"] >= 0) & (code != "") & ~np.isin(code, list(towns_const.LEFT_OUT))
        for _, pts, _ in work:  # a country pack's rules answered these
            todo[pts] = False
        pts = np.flatnonzero(todo)
        if not len(pts):
            return
        found = np.atleast_1d(self.layer.query(lat[pts], lon[pts])).astype(np.int64)
        hit = found >= 0
        hit[hit] = (self.country[found[hit]] == code[pts[hit]]) & (self.place[found[hit]] >= 0)
        pts, found = pts[hit], found[hit]
        if not len(pts):
            return
        head = self.place[found]
        scored = a["city"][pts]
        own = scored >= 0
        own[own] = self.cities.inside(self.key, scored[own]) == found[own]
        locality = np.where(own, scored, head)
        population = self.cities.table["population"]
        keeps = np.array(
            [
                o and s != h and not rolls_up(population[s], population[h])
                for o, s, h in zip(own.tolist(), scored.tolist(), head.tolist(), strict=True)
            ],
            dtype=bool,
        )
        a["town"][pts], a["town_place"][pts] = found, head
        a["town_locality"][pts] = locality
        a["town_city"][pts] = np.where(keeps, scored, head)
