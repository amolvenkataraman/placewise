"""Canada naming over the StatCan pack (census divisions and subdivisions, CMAs, FSAs).

- admin1: the subdivision's province ("can/csd:state").
- locality: the census subdivision (CSD), so amalgamated cities come out whole (Scarborough is in
  Toronto). Rural CSDs (townships, rural municipalities) and unorganised ones (improvement
  districts, unorganised territory) are named by the nearest GeoNames place inside them within
  RURAL_PLACE_KM; failing that a rural CSD is named itself and an unorganised one not at all.
- city: the locality if it has CITY_KEEP_POPULATION people or is named in its CMA's name;
  otherwise the CMA's first city (in the same province) when that city is CITY_ROLL_UP_RATIO
  times bigger (Pickering -> Toronto; Fort Erie stays). No locality: the GeoNames score.
- sublocality: the nearest GeoNames place within SUBLOCALITY_KM inside the same CSD.
- admin2 (census division), postal (forward sortation area), regions (the pack's curated
  `regions` and the CMA or CA, smallest first).
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import naming as const
from placewise.model import PlaceKind

from . import _common as common
from . import rules


class Can:
    country = "CA"

    @staticmethod
    def accepts(pack):
        return const.CAN_LAYERS["subdivision"] in pack

    def __init__(self, pack, layers, admin, cities):
        names = const.CAN_LAYERS
        self.layers, self.admin, self.cities = layers, admin, cities
        self.csd = layers.add(
            pack, names["subdivision"], common.area_maker(PlaceKind.LOCALITY, "csdtype", "province")
        )
        self.cd = self.cma = self.postal = self.regions = None
        if names["division"] in pack:
            self.cd = layers.add(
                pack, names["division"], common.area_maker(PlaceKind.ADMIN2, "cdtype", "province")
            )
        if names["postal"] in pack:
            self.postal = layers.add(
                pack, names["postal"], common.area_maker(PlaceKind.POSTAL_CODE, "province")
            )
        if names["metro"] in pack:
            self.cma = layers.add(pack, names["metro"], common.region_place)
        if const.REGIONS in pack:
            self.regions = layers.add(pack, const.REGIONS, common.region_place)

    def _col(self, key, field):
        values = self.layers.column(key, field)
        return values if values is not None else [""] * self.layers.layer(key).count

    @cached_property
    def _csd(self):
        provinces = self._col(self.csd, "province")
        row_of = self.admin.admin1_row_of_id
        kind = np.array([rules.csd_kind(t) for t in self._col(self.csd, "csdtype")], dtype=object)
        by_name = {}  # (province, folded name) -> the most populous CSD of that name
        pop = common.population(self.layers.layer(self.csd))
        for r in np.argsort(-np.nan_to_num(pop, nan=-1.0), kind="stable").tolist():
            by_name.setdefault((provinces[r], rules.fold(self._col(self.csd, "name")[r])), r)
        cd_row = {pid: i for i, pid in enumerate(self._col(self.cd, "id"))} if self.cd is not None else {}
        cduid = self.layers.column(self.csd, "cduid") or [
            i.rpartition(":")[2][:4] for i in self._col(self.csd, "id")
        ]
        return {
            "admin1": np.array([row_of.get(f"iso:CA-{p}", -1) for p in provinces], dtype=np.int64),
            "cd": np.array([cd_row.get(f"statcan:{c}", -1) for c in cduid], dtype=np.int64),
            "kind": kind,
            "population": pop,
            "by_name": by_name,
        }

    @cached_property
    def _cma(self):
        """Per CMA row: (the CSD row of its first city in its province or -1, folded title names)."""
        out = []
        by_name = self._csd["by_name"]
        for name, province in zip(self._col(self.cma, "name"), self._col(self.cma, "province"), strict=True):
            cities = rules.cma_cities(name)
            head = next(
                (by_name[province, rules.fold(c)] for c in cities if (province, rules.fold(c)) in by_name), -1
            )
            out.append((head, {rules.fold(c) for c in cities}))
        return out

    # -- the rules ----------------------------------------------------------------------------------

    def boundaries(self, a, pts, lat, lon):
        csd, rule = common.polygon(self.layers.layer(self.csd), lat, lon)
        admin1 = np.where(csd >= 0, self._csd["admin1"][np.maximum(csd, 0)], -1)
        fixed = admin1 >= 0
        a["aidx"][pts[fixed]] = admin1[fixed]
        return {"csd": csd, "rule": rule, "admin1": fixed}

    def names(self, a, pts, lat, lon, st):
        out = common.Named(len(pts), self.layers)
        every, csd = out.every, st["csd"]
        for i in np.flatnonzero(st["admin1"]).tolist():
            out.sources[i]["admin1"] = f"{self.csd}:{const.STATE}"
        if self.cd is not None:  # a CSD's division is its CSDUID's first four digits
            cd = np.where(csd >= 0, self._csd["cd"][np.maximum(csd, 0)], -1)
            out.put("admin2", every, self.cd, cd, st["rule"])
        local, local_km = a["local"][pts], a["local_km"][pts]
        kind = np.where(csd >= 0, self._csd["kind"][np.maximum(csd, 0)], "")
        # rural and unorganised subdivisions: the GeoNames place inside them, if one is near
        place = np.full(len(pts), -1, dtype=np.int64)
        rural = np.flatnonzero((kind == rules.RURAL) | (kind == rules.UNORGANIZED))
        place[rural] = common.geonames_inside(
            self.cities, self.csd, csd[rural], local[rural], local_km[rural], const.RURAL_PLACE_KM,
            lookup_const.CITY_EXCLUDED_FEATURE_CODES,
        )  # fmt: skip
        by_csd = ((kind == rules.MUNICIPAL) | (kind == rules.RURAL)) & (place < 0)
        locality = np.where(by_csd, csd, -1)
        out.put("locality", every, self.csd, locality, st["rule"])
        has = np.flatnonzero(place >= 0)
        out.put("locality", has, lookup_const.CITIES, place[has], const.INSIDE)
        pop = np.where(by_csd, self._csd["population"][np.maximum(csd, 0)], np.nan)
        pop[has] = self.cities.table["population"][place[has]]
        city, cma = self._city(out, lat, lon, locality, pop, st["rule"])
        none = np.flatnonzero(out.locality == None)  # noqa: E711 - element-wise
        out.put("city", none, lookup_const.CITIES, a["city"][pts[none]], lookup_const.SCORE)
        out.sublocality_inside(self.cities, self.csd, locality, local, local_km)
        if self.postal is not None:
            fsa = np.atleast_1d(self.layers.layer(self.postal).query(lat, lon)).astype(np.int64)
            out.put("postal", every, self.postal, fsa, lookup_const.POLYGON)
        common.set_regions(out, self.layers, lat, lon, self.regions, [(self.cma, cma)] if self.cma else ())
        common.skip_near(self.cities, self.csd, a, pts, locality, city)
        return out

    def _city(self, out, lat, lon, locality, pop, st_rule):
        """Fill out.city by the roll-up rule; returns (the city's CSD row per point, -1 for none or
        not a CSD; the CMA row per point)."""
        city = locality.copy()
        out.city[:] = out.locality
        for i in np.flatnonzero(out.locality != None).tolist():  # noqa: E711 - element-wise
            out.sources[i]["city"] = out.sources[i]["locality"]
        if self.cma is None:
            return city, np.full(len(lat), -1, dtype=np.int64)
        cma, _ = common.polygon(self.layers.layer(self.cma), lat, lon, snap_km=0)
        shore = np.flatnonzero((cma < 0) & (st_rule == lookup_const.NEAREST))  # off a clipped shore
        if len(shore):
            cma[shore] = common.polygon(self.layers.layer(self.cma), lat[shore], lon[shore])[0]
        population = self._csd["population"]
        for i in np.flatnonzero((cma >= 0) & (out.locality != None)).tolist():  # noqa: E711 - element-wise
            head, title = self._cma[cma[i]]
            if head < 0 or head == locality[i] or rules.fold(out.locality[i].name) in title:
                continue
            p, head_pop = pop[i], population[head]
            if rules.rolls_up(None if np.isnan(p) else p, None if np.isnan(head_pop) else head_pop):
                out.city[i] = self.layers.place(self.csd, int(head))
                out.sources[i]["city"] = f"{self.csd}:{const.METRO}"
                city[i] = head
        return city, cma
