"""India naming over the India pack (packbuild/README.md, India pack).

The pack's `states`, `districts` and `cities` are unions of PIN code areas keyed to the Local
Government Directory (LGD); a pack built before them has only `pincodes`, and the rules fall back
to it.

- admin1: the `states` feature's state (its ISO 3166-2:IN code, mapped to the world pack's older
  codes through constants.countries.ind), "ind/states:polygon"; without `states`, the PIN area's
  state, "ind/pincodes:state". Gurugram is in Haryana even where Natural Earth's coarse line says
  Delhi; the city score then prefers Haryana's cities.
- admin2: the `districts` feature (LGD district, with the name in use: Gurugram, Mysuru).
- locality and city: the `cities` feature (an urban local body drawn as its PIN areas: Bengaluru
  as the former BBMP area, Delhi's reunified corporation as one city); elsewhere the GeoNames score.
- sublocality: the nearest `neighbourhoods` point (a post office's name, "Koramangala S.O" ->
  Koramangala) of the point's own city within IND_NEIGHBOURHOOD_KM; else the PIN area's own post
  office without its type suffix ("Whitefield S.O" -> Whitefield), when it isn't the city's name.
- postal: the PIN code area; regions: the pack's curated `regions` layer when it has one.

Features flagged `india_view_only` (ground only India's view puts in India: Gilgit-Baltistan, the
part of Kashmir Pakistan administers, Aksai Chin, the Shaksgam valley) answer only when the IN
view decided the country.
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import naming as const
from placewise.constants.countries.ind import subregions
from placewise.constants.worldviews import IND_VIEW_ONLY
from placewise.model import Place, PlaceKind

from . import _common as common
from . import rules
from ._points import point_maker

NAMES = const.IND_LAYERS


class Ind:
    country = "IN"

    @staticmethod
    def accepts(pack):
        return NAMES["postal"] in pack

    def __init__(self, pack, layers, admin, cities):
        self.layers, self.admin, self.cities = layers, admin, cities
        # a PIN area is named by its code; its `name` is its head post office
        maker = common.area_maker(PlaceKind.POSTAL_CODE, "district", "state_code", name="pincode")
        self.pin = layers.add(pack, NAMES["postal"], maker)

        def optional(role, make):
            return layers.add(pack, NAMES[role], make) if NAMES[role] in pack else None

        self.state = optional("state", common.area_maker(PlaceKind.ADMIN1, "iso", "lgd"))
        self.district = optional("district", common.area_maker(PlaceKind.ADMIN2, "state_code", "lgd"))
        self.city = optional("city", common.area_maker(PlaceKind.LOCALITY, "state_code", "lgd", "type"))
        self.hoods = optional("neighbourhood", point_maker(PlaceKind.SUBLOCALITY))
        self.regions = layers.add(pack, const.REGIONS, common.region_place) if const.REGIONS in pack else None

    @cached_property
    def _admin1(self):
        """Per row of the states layer (else of the PIN areas), the world admin1 row of its state
        (new or replaced ISO code), or -1."""
        key, column = (self.state, "iso") if self.state is not None else (self.pin, "state_code")
        codes = self.layers.column(key, column) or [""] * self.layers.layer(key).count
        row_of = self.admin.admin1_row_of_id
        rows = {}
        for code in set(codes):
            state = subregions.BY_CODE.get(code.partition("-")[2])
            spellings = [code] + (
                [f"IN-{a}" for a in state.aliases if len(a) == 2 and a.isupper()] if state else []
            )
            rows[code] = next((row_of[f"iso:{s}"] for s in spellings if f"iso:{s}" in row_of), -1)
        return np.array([rows[c] for c in codes], dtype=np.int64)

    def _rows(self, key, a, pts, lat, lon, snap_km=const.SHORE_KM):
        """(rows, rules) of layer `key` per point: -1 where none, or where the feature is for
        India's view only and another view decided the country."""
        rows, rule = common.polygon(self.layers.layer(key), lat, lon, snap_km=snap_km)
        return self.admin.view_only(a, pts, rows, self.layers.column(key, IND_VIEW_ONLY), "IN"), rule

    def boundaries(self, a, pts, lat, lon):
        pin, rule = self._rows(self.pin, a, pts, lat, lon)
        if self.state is not None:
            state, _ = self._rows(self.state, a, pts, lat, lon)
            admin1 = np.where(state >= 0, self._admin1[np.maximum(state, 0)], -1)
        else:
            admin1 = np.where(pin >= 0, self._admin1[np.maximum(pin, 0)], -1)
        fixed = admin1 >= 0
        a["aidx"][pts[fixed]] = admin1[fixed]
        return {"pin": pin, "rule": rule, "admin1": fixed}

    def names(self, a, pts, lat, lon, st):
        out = common.Named(len(pts), self.layers)
        every, pin = out.every, st["pin"]
        admin1 = f"{self.state}:{lookup_const.POLYGON}" if self.state else f"{self.pin}:{const.STATE}"
        for i in np.flatnonzero(st["admin1"]).tolist():
            out.sources[i]["admin1"] = admin1
        out.put("postal", every, self.pin, pin, st["rule"])
        if self.district is not None:
            district, rule = self._rows(self.district, a, pts, lat, lon)
            out.put("admin2", every, self.district, district, rule)
        city = self._cities(a, pts, lat, lon, st["rule"])
        has, rest = np.flatnonzero(city >= 0), np.flatnonzero(city < 0)
        if len(has):
            for field in ("locality", "city"):
                out.put(field, has, self.city, city[has], lookup_const.POLYGON)
            common.skip_near(self.cities, self.city, a, pts, city, city)
        score = a["city"][pts[rest]]
        for field in ("locality", "city"):
            out.put(field, rest, lookup_const.CITIES, score, lookup_const.SCORE)
        self._sublocality(out, lat, lon, pin, city)
        if self.regions is not None:
            common.set_regions(out, self.layers, lat, lon, self.regions)
        return out

    def _cities(self, a, pts, lat, lon, pin_rule):
        """The cities row per point (-1: none): the containing city; a point in no PIN area (off
        the shore) reaches the nearest within SHORE_KM."""
        if self.city is None:
            return np.full(len(pts), -1, dtype=np.int64)
        city, _ = self._rows(self.city, a, pts, lat, lon, snap_km=0)
        off = np.flatnonzero((city < 0) & (pin_rule != lookup_const.POLYGON))
        if len(off):
            city[off], _ = self._rows(self.city, a, pts[off], lat[off], lon[off])
        return city

    def _sublocality(self, out, lat, lon, pin, city):
        """The nearest neighbourhood of the point's city, else the PIN area's office name."""
        found = np.full(len(lat), -1, dtype=np.int64)
        if self.hoods is not None and (city >= 0).any():
            found = self._neighbourhoods(out, lat, lon, city)
            has = np.flatnonzero(found >= 0)
            out.put("sublocality", has, self.hoods, found[has], lookup_const.NEAREST)
        for i in np.flatnonzero((pin >= 0) & (found < 0)).tolist():
            area = self._area(int(pin[i]))
            named = (out.locality[i], out.city[i])
            if area is not None and not any(
                p is not None and rules.same_name(area.name, p.name) for p in named
            ):
                out.sublocality[i] = area
                out.sources[i]["sublocality"] = f"{self.pin}:{const.NAME}"

    def _neighbourhoods(self, out, lat, lon, city):
        """Per point, the nearest neighbourhood row within IND_NEIGHBOURHOOD_KM whose city is the
        point's own and whose name isn't the locality's; -1 for none."""
        layer = self.layers.layer(self.hoods)
        k = min(const.IND_NEIGHBOURHOOD_CANDIDATES, max(layer.count, 1))
        rows, _ = layer.nearest(lat, lon, k=k, max_km=const.IND_NEIGHBOURHOOD_KM)
        rows = np.asarray(rows).reshape(len(lat), -1)
        city_ids = self.layers.column(self.city, "id")
        hood_city, names = self.layers.column(self.hoods, "city"), self.layers.column(self.hoods, "name")
        found = np.full(len(lat), -1, dtype=np.int64)
        for i in np.flatnonzero(city >= 0).tolist():
            own = city_ids[city[i]].partition("#")[0]
            for r in rows[i].tolist():
                if r >= 0 and hood_city[r] == own and not rules.same_name(names[r], out.locality[i].name):
                    found[i] = r
                    break
        return found

    def _area(self, row):
        """The neighbourhood a PIN area's post office names, as a sublocality (made once)."""
        cache = self.layers.cache(f"{self.pin}#area")
        if row not in cache:
            postal = self.layers.place(self.pin, row)
            office = self.layers.column(self.pin, "name")[row]
            name = rules.office_area_name(office) if office else ""
            cache[row] = (
                Place(
                    f"indiapost:{postal.name}:{office}",
                    name,
                    PlaceKind.SUBLOCALITY,
                    bbox=postal.bbox,
                    source=postal.source,
                )
                if name and not name.isdigit()
                else None
            )
        return cache[row]
