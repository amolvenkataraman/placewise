"""Naming over the COD-AB country packs (OCHA administrative boundaries, constants/codab.py): one rule
for every such country, configured per country by `placewise.constants.codab.COUNTRIES`.

- The point is looked up once, in the deepest level the pack has (snapping to the nearest unit
  within SHORE_KM, for coasts); the levels above come from each unit's `parent`, so the answers
  always nest.
- admin1: when the world pack's admin1 is the same unit (`world_admin1`) and one of the country's
  has the ADM1's name, that world admin1 stays (with its ISO code: "<finest>:state"); otherwise the
  ADM1 answers admin1, by its COD-AB name ("<pack>/admin1:parent", or ":polygon" when ADM1 is
  the deepest level). Levels read from a parent have rule "parent".
- admin2: the configured level (district, amphoe, municipio, ilce ...).
- locality: the configured municipal level where there is one (Nepal's local levels), else the
  GeoNames score, as everywhere else; city: the GeoNames score.
- sublocality: the configured level below the locality (Sri Lanka's Grama Niladhari divisions,
  Thailand's tambon) unless it is named like the locality or city; where the locality is a COD-AB
  municipality and no level is configured, the nearest GeoNames place inside it (SUBLOCALITY_KM).
"""

from functools import cached_property

import numpy as np

from placewise.constants import codab as codab_const
from placewise.constants import lookup as lookup_const
from placewise.constants import naming as const
from placewise.model import Place, PlaceKind

from .._layers import source_of
from . import _common as common
from . import rules


class Codab:
    @staticmethod
    def accepts(pack):
        return pack.name in codab_const.COUNTRIES and f"{codab_const.LAYER_PREFIX}1" in pack

    def __init__(self, pack, layers, admin, cities):
        self.config = config = codab_const.COUNTRIES[pack.name]
        self.country = config.iso2
        self.layers, self.admin, self.cities = layers, admin, cities
        kinds = {config.admin2: PlaceKind.ADMIN2, config.locality: PlaceKind.LOCALITY}
        kinds[config.sublocality] = PlaceKind.SUBLOCALITY
        self.keys = {}
        for n in range(1, config.levels + 1):
            name = f"{codab_const.LAYER_PREFIX}{n}"
            if name not in pack:
                break
            kind = PlaceKind.ADMIN1 if n == 1 else kinds.get(n, PlaceKind.ADMIN2)
            suffix = config.admin1_suffix if n == 1 else ""
            self.keys[n] = layers.add(pack, name, _maker(kind, config.iso2, suffix))
        self.finest = max(self.keys)

    def _level(self, n):
        return n if n is not None and n in self.keys else None

    @cached_property
    def _parents(self):
        """Per level n >= 2, each unit's row in level n - 1 (-1 when its parent is missing)."""
        out = {}
        for n in range(2, self.finest + 1):
            above = {pid: i for i, pid in enumerate(self.layers.column(self.keys[n - 1], "id"))}
            parents = self.layers.column(self.keys[n], "parent") or []
            out[n] = np.array([above.get(p, -1) for p in parents], dtype=np.int64)
        return out

    @cached_property
    def _world_admin1(self):
        """Per ADM1 row, the world admin1 row of the same name in this country, or -1."""
        names = self.layers.column(self.keys[1], "name")
        if not self.config.world_admin1 or self.admin.admin1 is None:
            return np.full(len(names), -1, dtype=np.int64)
        world = self.admin.admin1
        country = world.column("country").tolist() if "country" in world.fields else [""] * world.count
        by_name = {}
        for i, (name, code) in enumerate(zip(world.column("name").tolist(), country, strict=True)):
            if code == self.country:
                by_name.setdefault(rules.fold(name), i)
        return np.array([by_name.get(rules.fold(n), -1) for n in names], dtype=np.int64)

    # -- the rules ----------------------------------------------------------------------------------

    def boundaries(self, a, pts, lat, lon):
        rows, rule = common.polygon(self.layers.layer(self.keys[self.finest]), lat, lon)
        chain = {self.finest: rows}
        for n in range(self.finest, 1, -1):
            up = chain[n]
            chain[n - 1] = np.where(up >= 0, self._parents[n][np.maximum(up, 0)], -1)
        adm1 = chain[1]
        world = np.where(adm1 >= 0, self._world_admin1[np.maximum(adm1, 0)], -1)
        kept = world >= 0
        a["aidx"][pts[kept]] = world[kept]
        return {"rows": chain, "rule": rule, "world": kept}

    def names(self, a, pts, lat, lon, st):
        m, layers = len(pts), self.layers
        out = common.Named(m, layers)
        out.admin1 = np.full(m, None, dtype=object)
        every, chain = out.every, st["rows"]
        parent = np.full(m, codab_const.PARENT, dtype=object)

        def rule(n):  # the deepest level was looked up; the ones above are its parents
            return st["rule"] if n == self.finest else parent

        for i in np.flatnonzero(st["world"]).tolist():
            out.sources[i]["admin1"] = f"{self.keys[self.finest]}:{const.STATE}"
        own = np.flatnonzero(~st["world"] & (chain[1] >= 0))
        out.put("admin1", own, self.keys[1], chain[1][own], rule(1)[own])
        if (n := self._level(self.config.admin2)) is not None:
            out.put("admin2", every, self.keys[n], chain[n], rule(n))
        city = common.places_for(layers, lookup_const.CITIES, a["city"][pts])
        score = layers.source(lookup_const.CITIES, lookup_const.SCORE)
        out.set("city", every, city, score)
        local = self._level(self.config.locality)
        locality = chain[local] if local is not None else np.full(m, -1, dtype=np.int64)
        if local is not None:
            out.put("locality", every, self.keys[local], locality, rule(local))
        none = np.flatnonzero(out.locality == None)  # noqa: E711 - element-wise
        out.set("locality", none, city[none], score)
        if (sub := self._level(self.config.sublocality)) is not None:
            places = common.places_for(layers, self.keys[sub], chain[sub], PlaceKind.SUBLOCALITY)
            sources = rule(sub).tolist()
            for i, p in enumerate(places.tolist()):
                if p is not None and not any(
                    q is not None and rules.same_name(p.name, q.name) for q in (out.locality[i], out.city[i])
                ):
                    out.sublocality[i] = p
                    out.sources[i]["sublocality"] = layers.source(self.keys[sub], sources[i])
        elif local is not None:
            out.sublocality_inside(
                self.cities, self.keys[local], locality, a["local"][pts], a["local_km"][pts]
            )
        if local is not None:
            common.skip_near(self.cities, self.keys[local], a, pts, locality, locality)
        return out


def _maker(kind, iso2, suffix=""):
    """Places of a COD-AB layer: `kind`, the English name (plus `suffix`), the P-code and type. A
    unit the package gives no English name names nothing (None)."""

    def make(get, layer, i):
        if not get("name"):
            return None
        found = {"pcode": get("pcode"), "country": iso2}
        if get("type"):
            found["type"] = get("type")
        return Place(
            get("id"), get("name") + suffix, kind, bbox=layer.bbox(i), codes=found, source=source_of(layer)
        )

    return make
