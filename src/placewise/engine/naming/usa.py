"""United States naming over the Census Bureau pack (counties, places, ZCTAs, CBSAs, CSAs).

- admin1: the county's state ("usa/counties:state").
- locality: the census place containing the point; inside a metro area, the ZIP Code's postal
  city (the ZCTA's `postal_place`, within POSTAL_CITY_KM) corrects how people talk:
  - a census-designated place (CDP) takes its postal city when that is an incorporated place
    (Paradise -> Las Vegas), unless the CDP's own name extends it (East Los Angeles stays, under
    Los Angeles); a CDP of fewer than CDP_KEEP_POPULATION people also takes a postal city that is
    another CDP. The CDP is then the sublocality.
  - unincorporated land (no place) takes its postal city (SFO -> San Francisco).
  Incorporated places are always themselves.
- city: the locality; for a CDP that keeps its name, its incorporated postal city (East Los
  Angeles -> Los Angeles). No locality: the metro's largest principal city in the state (OMB list
  2) within METRO_CITY_KM, else the GeoNames score.
- sublocality: the nearest GeoNames place within SUBLOCALITY_KM inside the same census place.
- borough (New York City's five counties), admin2 (county), postal (ZCTA, from the optional usa-zip
  pack; without it, none), regions (the pack's curated `regions` and the CBSA and CSA, smallest
  first).

The postal city is the ZCTA's `postal_place`: from the ZCTAs when usa-zip is open, else from the
usa pack's `postal_cities` (the same areas, kept only where a postal city can name a locality:
packbuild.us_zip), so the locality is the same either way.
"""

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import naming as const
from placewise.model import Place, PlaceKind
from placewise.packs import once

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
        self.postal = self.postal_cities = self.cbsa = self.csa = self.regions = None
        if names["postal"] in pack:  # packs built before the ZIP Code areas moved to usa-zip
            self.postal = layers.add(pack, names["postal"], common.area_maker(PlaceKind.POSTAL_CODE))
        if names["postal_cities"] in pack:
            self.postal_cities = layers.add(pack, names["postal_cities"])
        if const.REGIONS in pack:
            self.regions = layers.add(pack, const.REGIONS, common.region_place)
        # the CBSA names the principal cities, whichever regions the Result lists
        if names["cbsa"] in pack:
            self.cbsa = layers.add(pack, names["cbsa"], common.region_place)
        if names["csa"] in pack:
            self.csa = layers.add(pack, names["csa"], common.region_place)

    def add_packs(self, packs):
        """The ZIP Code areas from the usa-zip pack, when it is open and the usa pack lacks them."""
        zips = next((p for p in packs if const.USA_LAYERS["postal"] in p), None)
        if self.postal is None and zips is not None:
            self.postal = self.layers.add(
                zips, const.USA_LAYERS["postal"], common.area_maker(PlaceKind.POSTAL_CODE)
            )

    @property
    def _postal_areas(self):
        """The layer whose areas carry the postal cities: the ZIP Code areas when open (they also
        give `postal`), else the usa pack's postal_cities (the same areas, where they can matter)."""
        return self.postal if self.postal is not None else self.postal_cities

    # -- per-row tables -----------------------------------------------------------------------------

    def _col(self, key, field):
        values = self.layers.column(key, field) if key is not None else None
        return values if values is not None else [""] * (self.layers.layer(key).count if key else 0)

    @once
    def _place(self):
        ids = self._col(self.place, "id")
        return {
            "incorporated": np.array(
                [c == "incorporated" for c in self._col(self.place, "class")], dtype=bool
            ),
            "population": common.population(self.layers.layer(self.place)),
            "row_of": {pid: r for r, pid in enumerate(ids)},
        }

    @once
    def _county(self):
        ids, states = self._col(self.county, "id"), self._col(self.county, "state")
        row_of = self.admin.admin1_row_of_id
        admin1 = np.array([row_of.get(f"iso:US-{s}", -1) for s in states], dtype=np.int64)
        borough = [const.NYC_BOROUGHS.get(i.rpartition(":")[2]) for i in ids]
        cbsa = self._member_rows(self.cbsa, self._col(self.county, "cbsa"))
        metro = np.array([t == "metro" for t in self._col(self.cbsa, "type")] + [False], dtype=bool)
        return {
            "admin1": admin1,
            "borough": borough,
            "cbsa": cbsa,
            "metro": metro[cbsa],  # index -1 is the False sentinel
            "csa": self._member_rows(self.csa, self._col(self.county, "csa")),
            "head": self._heads(cbsa, states),
        }

    def _member_rows(self, key, codes):
        """Per county, the row of the CBSA / CSA its code names, -1 for none."""
        if key is None:
            return np.full(len(codes), -1, dtype=np.int64)
        row_of = {c: i for i, c in enumerate(self._col(key, "code"))}
        return np.array([row_of.get(c, -1) if c else -1 for c in codes], dtype=np.int64)

    def _heads(self, cbsa, states):
        """Per county, the place row of its CBSA's largest principal city in the county's state
        (principal_cities lists them largest first), -1 for none."""
        row_of, place_states = self._place["row_of"], self._col(self.place, "state")
        lists = [
            [row_of[i] for i in (s or "").split(",") if i in row_of]
            for s in self._col(self.cbsa, "principal_cities")
        ]
        out = np.full(len(cbsa), -1, dtype=np.int64)
        for c, (row, state) in enumerate(zip(cbsa.tolist(), states, strict=True)):
            if row >= 0:
                out[c] = next((p for p in lists[row] if place_states[p] == state), -1)
        return out

    @once
    def _zcta(self):
        """Per row of the postal areas, the place row of its postal city (-1: none or not a place
        in the pack)."""
        row_of = self._place["row_of"]
        return np.array(
            [row_of.get(p or "", -1) for p in self._col(self._postal_areas, "postal_place")], dtype=np.int64
        )

    # -- the rules ----------------------------------------------------------------------------------

    def tz_layer(self):
        """The counties' key when they carry their time zone (placewise.engine._timezones), else None."""
        return common.tz_layer(self.layers, self.county)

    def tz_rows(self, state):
        """Per point of `boundaries`, the county it lies inside (-1: none, or only near one)."""
        return common.inside_rows(state["county"], state["rule"])

    def boundaries(self, a, pts, lat, lon):
        county, rule = common.polygon(self.layers.layer(self.county), lat, lon)
        admin1 = np.where(county >= 0, self._county["admin1"][np.maximum(county, 0)], -1)
        fixed = admin1 >= 0
        a["aidx"][pts[fixed]] = admin1[fixed]
        return {"county": county, "rule": rule, "admin1": fixed}

    def names(self, a, pts, lat, lon, st):
        out = common.Named(len(pts), self.layers)
        every, county = out.every, st["county"]
        safe = np.maximum(county, 0)
        out.put("admin2", every, self.county, county, st["rule"])
        for i in np.flatnonzero(st["admin1"]).tolist():
            out.sources[i]["admin1"] = f"{self.county}:{const.STATE}"
        place, prule = self._places(lat, lon, st["rule"])
        zcta = np.full(len(pts), -1, dtype=np.int64)
        if self._postal_areas is not None:
            zcta = np.atleast_1d(self.layers.layer(self._postal_areas).query(lat, lon)).astype(np.int64)
        if self.postal is not None:
            out.put("postal", every, self.postal, zcta, lookup_const.POLYGON)
        metro = (county >= 0) & self._county["metro"][safe]
        postal = self._postal_cities(lat, lon, zcta, place, metro)
        locality, city, lrule, crule, rolled = self._locality(place, prule, postal)
        # no locality: the metro's largest principal city in the state, if near
        head = np.where(county >= 0, self._county["head"][safe], -1)
        head = self._within(lat, lon, np.where(locality < 0, head, -1), const.METRO_CITY_KM)
        took = (locality < 0) & (head >= 0)
        city[took], crule[took] = head[took], const.METRO
        out.put("locality", every, self.place, locality, lrule)
        out.put("city", every, self.place, city, crule)
        fallback = np.flatnonzero(city < 0)
        out.put("city", fallback, lookup_const.CITIES, a["city"][pts[fallback]], lookup_const.SCORE)
        self._borough(out, county)
        found = out.sublocality_inside(self.cities, self.place, place, a["local"][pts], a["local_km"][pts])
        cdp_itself = np.flatnonzero(rolled & (found < 0))  # the CDP, under its postal city
        out.put(
            "sublocality",
            cdp_itself,
            self.place,
            place[cdp_itself],
            lookup_const.POLYGON,
            PlaceKind.SUBLOCALITY,
        )
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

    def _postal_cities(self, lat, lon, zcta, place, metro):
        """Per point, the place row of its ZCTA's postal city when the point is in a metro area,
        the city isn't the point's own place and its boundary is within POSTAL_CITY_KM; else -1."""
        postal = np.where((zcta >= 0) & metro, self._zcta[np.maximum(zcta, 0)] if len(self._zcta) else -1, -1)
        postal[postal == place] = -1
        return self._within(lat, lon, postal, const.POSTAL_CITY_KM)

    def _locality(self, place, prule, postal):
        """(locality, city, their rules, which points' CDP gave way to its postal city), by the
        module's rules. Rows are place rows, -1 for none."""
        tables = self._place
        inc = tables["incorporated"]
        has, safe, psafe = place >= 0, np.maximum(place, 0), np.maximum(postal, 0)
        cdp = has & ~inc[safe]
        postal_inc = (postal >= 0) & inc[psafe]
        extends = np.zeros(len(place), dtype=bool)
        for i in np.flatnonzero(cdp & postal_inc).tolist():
            names = [self.layers.value(self.place, "name", int(r)) for r in (place[i], postal[i])]
            extends[i] = rules.extends(*names)
        small = tables["population"][safe] < const.CDP_KEEP_POPULATION  # NaN (unknown): not small
        rolled = cdp & (postal >= 0) & ((postal_inc & ~extends) | (~postal_inc & small))
        takes = rolled | (~has & (postal >= 0))
        locality = np.where(takes, postal, place)
        lrule = np.where(takes, const.POSTAL, prule).astype(object)
        under = cdp & ~rolled & postal_inc  # a CDP keeping its name, under its postal city
        city = np.where(under, postal, locality)
        crule = np.where(under, const.POSTAL, lrule).astype(object)
        return locality, city, lrule, crule, rolled

    def _within(self, lat, lon, rows, km):
        """`rows` (place rows, -1 for none) with those whose boundary is farther than km from the
        point set to -1 (internal points can be far off: San Francisco's is on the Farallon
        Islands)."""
        layer, out = self.layers.layer(self.place), rows.copy()
        out[~common.near_bbox(layer.bboxes(), out, lat, lon, km)] = -1  # cheap test first
        group = np.flatnonzero(out >= 0)  # each point to its own place's boundary, at once
        km_away = np.atleast_1d(layer.nearest_edge_km(lat[group], lon[group], out[group]))
        out[group[km_away > np.broadcast_to(km, out.shape)[group]]] = -1
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
