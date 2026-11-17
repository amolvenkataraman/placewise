"""United States naming over the Census Bureau pack (counties, places, ZCTAs, CBSAs, CSAs).

- admin1: the county's state ("usa/counties:state").
- locality: the census place containing the point. A census-designated place (CDP) inside a metro
  area takes the CBSA title's first city in its state, when the point is within METRO_CDP_KM of
  that city and the CDP isn't named in the title itself (Paradise -> Las Vegas; Arlington VA and
  Stanford stay): the stand-in for the ZIP Code's postal city. The CDP is then the sublocality.
  Unincorporated land (no place) has no locality.
- city: the locality; on unincorporated land the metro's city within METRO_CITY_KM (SFO -> San
  Francisco), else the GeoNames score. Incorporated places are always their own city (Emeryville).
- sublocality: the nearest GeoNames place within SUBLOCALITY_KM inside the same census place.
- borough (New York City's five counties), admin2 (county), postal (ZCTA), regions (the pack's
  curated `regions` and the CBSA and CSA, smallest first).
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import naming as const
from placewise.model import Place, PlaceKind

from . import _common as common
from . import rules


class Usa:
    country = "US"

    @staticmethod
    def accepts(pack):
        return const.USA_LAYERS["county"] in pack and const.USA_LAYERS["place"] in pack

    def __init__(self, pack, layers, admin, cities):
        names = const.USA_LAYERS
        self.layers, self.admin, self.cities = layers, admin, cities
        self.county = layers.add(pack, names["county"], common.area_maker(PlaceKind.ADMIN2, "state"))
        self.place = layers.add(pack, names["place"], common.area_maker(PlaceKind.LOCALITY, "state", "class"))
        self.postal = self.cbsa = self.csa = self.regions = None
        if names["postal"] in pack:
            self.postal = layers.add(pack, names["postal"], common.area_maker(PlaceKind.POSTAL_CODE))
        if const.REGIONS in pack:
            self.regions = layers.add(pack, const.REGIONS, common.region_place)
        # the CBSA names the principal cities, whichever regions the Result lists
        if names["cbsa"] in pack:
            self.cbsa = layers.add(pack, names["cbsa"], common.region_place)
        if names["csa"] in pack:
            self.csa = layers.add(pack, names["csa"], common.region_place)
        self._heads = {}

    # -- per-row tables -----------------------------------------------------------------------------

    def _col(self, key, field):
        values = self.layers.column(key, field)
        return values if values is not None else [""] * self.layers.layer(key).count

    @cached_property
    def _county(self):
        ids, states = self._col(self.county, "id"), self._col(self.county, "state")
        row_of = self.admin.admin1_row_of_id
        admin1 = np.array([row_of.get(f"iso:US-{s}", -1) for s in states], dtype=np.int64)
        borough = [const.NYC_BOROUGHS.get(i.rpartition(":")[2]) for i in ids]
        return {
            "admin1": admin1,
            "state": states,
            "borough": borough,
            "cbsa": self._member_rows(self.cbsa, self._col(self.county, "cbsa")),
            "csa": self._member_rows(self.csa, self._col(self.county, "csa")),
        }

    def _member_rows(self, key, codes):
        """Per county, the row of the CBSA / CSA its code names, -1 for none."""
        if key is None:
            return np.full(len(codes), -1, dtype=np.int64)
        row_of = {c: i for i, c in enumerate(self._col(key, "code"))}
        return np.array([row_of.get(c, -1) if c else -1 for c in codes], dtype=np.int64)

    @cached_property
    def _place(self):
        layer = self.layers.layer(self.place)
        names, states = self._col(self.place, "name"), self._col(self.place, "state")
        incorporated = np.array([c == "incorporated" for c in self._col(self.place, "class")], dtype=bool)
        pop = common.population(layer)
        by_name = {}  # (state, name) -> row: incorporated first, then the most people
        rank = np.lexsort((-np.nan_to_num(pop, nan=-1.0), ~incorporated))
        for r in rank.tolist():
            by_name.setdefault((states[r], names[r]), r)

        return {
            "incorporated": incorporated,
            "by_name": by_name,
        }

    def _head(self, cbsa, state):
        """(place row of the CBSA title's first city in `state` or -1, folded title names)."""
        key = (cbsa, state)
        if key not in self._heads:
            title = self._col(self.cbsa, "title")[cbsa] if self.cbsa is not None and cbsa >= 0 else ""
            states = rules.title_states(title)
            by_name = self._place["by_name"]
            cities = rules.title_cities(title, lambda n: any((s, n) in by_name for s in states))
            head = next((by_name[state, n] for n in cities if (state, n) in by_name), -1)
            self._heads[key] = (head, {rules.fold(n) for n in cities})
        return self._heads[key]

    # -- the rules ----------------------------------------------------------------------------------

    def boundaries(self, a, pts, lat, lon):
        county, rule = common.polygon(self.layers.layer(self.county), lat, lon)
        admin1 = np.where(county >= 0, self._county["admin1"][np.maximum(county, 0)], -1)
        fixed = admin1 >= 0
        a["aidx"][pts[fixed]] = admin1[fixed]
        return {"county": county, "rule": rule, "admin1": fixed}

    def names(self, a, pts, lat, lon, st):
        out = common.Named(len(pts), self.layers)
        every, county = out.every, st["county"]
        out.put("admin2", every, self.county, county, st["rule"])
        for i in np.flatnonzero(st["admin1"]).tolist():
            out.sources[i]["admin1"] = f"{self.county}:{const.STATE}"
        place, prule = self._places(lat, lon, st["rule"])
        inc = (place >= 0) & self._place["incorporated"][np.maximum(place, 0)]
        cdp = (place >= 0) & ~inc
        head = self._metro_heads(lat, lon, county, place, cdp | (place < 0))
        rolled = cdp & (head >= 0)
        locality = np.where(rolled, head, place)
        lrule = np.where(rolled, const.METRO, prule)
        out.put("locality", every, self.place, locality, lrule)
        # the city: the locality; on unincorporated land the metro's city, else the GeoNames score
        city = np.where(place < 0, head, locality)
        out.put("city", every, self.place, city, np.where(place < 0, const.METRO, lrule))
        fallback = np.flatnonzero(city < 0)
        out.put("city", fallback, lookup_const.CITIES, a["city"][pts[fallback]], lookup_const.SCORE)
        self._borough(out, county)
        found = out.sublocality_inside(self.cities, self.place, place, a["local"][pts], a["local_km"][pts])
        cdp_itself = np.flatnonzero(rolled & (found < 0))  # the CDP, under its metro's city
        out.put(
            "sublocality",
            cdp_itself,
            self.place,
            place[cdp_itself],
            lookup_const.POLYGON,
            PlaceKind.SUBLOCALITY,
        )
        if self.postal is not None:
            zcta = np.atleast_1d(self.layers.layer(self.postal).query(lat, lon)).astype(np.int64)
            out.put("postal", every, self.postal, zcta, lookup_const.POLYGON)
        self._regions(out, lat, lon, county)
        common.skip_near(self.cities, self.place, a, pts, locality, city)
        return out

    def _places(self, lat, lon, county_rule):
        """The census place per point; points off the clipped shore (no county) reach the nearest."""
        layer = self.layers.layer(self.place)
        place, rule = common.polygon(layer, lat, lon, snap_km=0)
        water = np.flatnonzero((place < 0) & (county_rule != lookup_const.POLYGON))
        if len(water):
            place[water], rule[water] = common.polygon(layer, lat[water], lon[water])
        return place, rule

    def _metro_heads(self, lat, lon, county, place, want):
        """Per point, the place row of its metro's city (see the module rules), or -1."""
        out = np.full(len(lat), -1, dtype=np.int64)
        tables, names = self._county, self.layers.column(self.place, "name")
        for i in np.flatnonzero(want & (county >= 0)).tolist():
            c = county[i]
            head, title = self._head(int(tables["cbsa"][c]), tables["state"][c])
            if head >= 0 and not (place[i] >= 0 and rules.fold(names[place[i]]) in title):
                out[i] = head
        # near enough: within METRO_CITY_KM of the city's boundary (internal points can be far
        # off: San Francisco's is on the Farallon Islands)
        layer = self.layers.layer(self.place)
        limit = np.where(place >= 0, const.METRO_CDP_KM, const.METRO_CITY_KM)
        out[~common.near_bbox(layer.bboxes(), out, lat, lon, limit)] = -1  # cheap test first
        group = np.flatnonzero(out >= 0)
        km = np.atleast_1d(layer.nearest_edge_km(lat[group], lon[group], out[group]))
        out[group[km > limit[group]]] = -1
        return out

    def _borough(self, out, county):
        borough = self._county["borough"]
        for i in np.flatnonzero(county >= 0).tolist():
            name = borough[county[i]]
            if name:
                base = self.layers.place(self.county, int(county[i]))
                place = Place(base.id, name, PlaceKind.BOROUGH, bbox=base.bbox, source=base.source)
                out.borough[i] = place
                out.sources[i]["borough"] = f"{self.county}:{const.NAME}"

    def _regions(self, out, lat, lon, county):
        safe, statistical = np.maximum(county, 0), []
        for key, column in ((self.cbsa, "cbsa"), (self.csa, "csa")):
            if key is not None:
                statistical.append((key, np.where(county >= 0, self._county[column][safe], -1)))
        common.set_regions(out, self.layers, lat, lon, self.regions, statistical)
