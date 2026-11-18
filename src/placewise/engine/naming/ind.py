"""India naming over the India Post pack (PIN code areas).

India has no open municipal or state polygons yet (packbuild/README.md), so:

- admin1: the PIN area's state (`state_code`, ISO 3166-2:IN after 2023, mapped to the world pack's
  older codes through constants.countries.ind), "ind/pincodes:state". Gurugram is in Haryana even
  where Natural Earth's coarse line says Delhi; the city score then prefers Haryana's cities.
- locality and city: the GeoNames score, as for the rest of the world.
- sublocality: the PIN area's post office without its type suffix ("Whitefield S.O" ->
  Whitefield), when it isn't the city's own name.
- postal: the PIN code area; regions: the pack's curated `regions` layer when it has one.
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


class Ind:
    country = "IN"

    @staticmethod
    def accepts(pack):
        return const.IND_LAYERS["postal"] in pack

    def __init__(self, pack, layers, admin, cities):
        self.layers, self.admin, self.cities = layers, admin, cities
        # a PIN area is named by its code; its `name` is its head post office
        maker = common.area_maker(PlaceKind.POSTAL_CODE, "district", "state_code", name="pincode")
        self.pin = layers.add(pack, const.IND_LAYERS["postal"], maker)
        self.regions = layers.add(pack, const.REGIONS, common.region_place) if const.REGIONS in pack else None

    @cached_property
    def _admin1(self):
        """Per PIN area, the world admin1 row of its state (new or replaced ISO code), or -1."""
        row_of = self.admin.admin1_row_of_id
        codes = self.layers.column(self.pin, "state_code") or [""] * self.layers.layer(self.pin).count
        rows = {}
        for code in set(codes):
            state = subregions.BY_CODE.get(code.partition("-")[2])
            spellings = [code] + (
                [f"IN-{a}" for a in state.aliases if len(a) == 2 and a.isupper()] if state else []
            )
            rows[code] = next((row_of[f"iso:{s}"] for s in spellings if f"iso:{s}" in row_of), -1)
        return np.array([rows[c] for c in codes], dtype=np.int64)

    def boundaries(self, a, pts, lat, lon):
        pin, rule = common.polygon(self.layers.layer(self.pin), lat, lon)
        # PIN areas on ground only India's view puts in India answer only under that view
        pin = self.admin.view_only(a, pts, pin, self.layers.column(self.pin, IND_VIEW_ONLY), "IN")
        admin1 = np.where(pin >= 0, self._admin1[np.maximum(pin, 0)], -1)
        fixed = admin1 >= 0
        a["aidx"][pts[fixed]] = admin1[fixed]
        return {"pin": pin, "rule": rule, "admin1": fixed}

    def names(self, a, pts, lat, lon, st):
        m, layers, every = len(pts), self.layers, np.arange(len(pts))
        out = common.Named(m, layers)
        pin, rule = st["pin"], st["rule"]
        for i in np.flatnonzero(st["admin1"]).tolist():
            out.sources[i]["admin1"] = f"{self.pin}:{const.STATE}"
        out.set(
            "postal",
            every,
            common.places_for(layers, self.pin, pin),
            [f"{self.pin}:{r}" for r in rule.tolist()],
        )
        city = a["city"][pts]
        places = common.places_for(layers, lookup_const.CITIES, city)
        source = layers.source(lookup_const.CITIES, lookup_const.SCORE)
        out.set("city", every, places, source)
        out.set("locality", every, places, source)
        for i in np.flatnonzero(pin >= 0).tolist():
            area = self._area(int(pin[i]))
            if area is not None and not (
                places[i] is not None and rules.same_name(area.name, places[i].name)
            ):
                out.sublocality[i] = area
                out.sources[i]["sublocality"] = f"{self.pin}:{const.NAME}"
        if self.regions is not None:
            common.set_regions(out, layers, lat, lon, self.regions)
        return out

    def _area(self, row):
        """The neighbourhood a PIN area's post office names, as a sublocality (made once)."""
        cache = self.layers.cache(f"{self.pin}#area")
        if row not in cache:
            postal = self.layers.place(self.pin, row)
            office = self.layers.value(self.pin, "name", row)
            code = postal.name
            name = rules.office_area_name(office) if office else ""
            cache[row] = (
                Place(
                    f"indiapost:{code}:{office}",
                    name,
                    PlaceKind.SUBLOCALITY,
                    bbox=postal.bbox,
                    source=postal.source,
                )
                if name and not name.isdigit()
                else None
            )
        return cache[row]
