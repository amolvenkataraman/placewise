"""Time zones from the packs' `timezones` polygons (packbuild/timezones.py, docs/timezones.md).

For every point on land or within the territorial sea (country known), in this order:

1. worldview: where the worldview reports the point in another country than the one administering
   it, and that country has one zone, that zone (rule "worldview");
2. country packs (usa, can ...), finest first: on ground whose data agrees, in that pack's country,
   the first feature of its layer containing the point (rule "polygon");
3. the world pack's layer: the point's own unit, found through the admin answer already made (a
   shape of its country containing it, else its admin-1 unit's feature, else its country's), so the
   zone nests exactly in the country and admin-1 answers (rule "polygon", or "offshore" when the
   country is the one within TERRITORIAL_KM). A timezones layer in a pack without the countries
   layer is answered by geometry instead: the first feature of the point's country containing it.

A feature whose `zones` lists several zones is split along a line the packs don't draw: the
nearest GeoNames city inside that feature whose zone is one of them decides (rule "split"), else
its first zone. A feature with zone "" has none (tzdb records no zone there). Points left without a
zone keep the nearest-city rule (placewise.engine._cities, "world/cities:nearest"); far at sea,
none.

Fills a["tz_zone"] (zone or None per point) and a["tz_source"] ("world/timezones:polygon" ...).
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as const

from ._index import RowIndex


class Timezones:
    def __init__(self, layers, admin):
        self.layers, self.admin = layers, admin
        world_pack = layers.world(const.COUNTRIES)
        world_pack = world_pack.split("/")[0] if world_pack else None
        self.world, self.country_keys, self.geometric = None, [], []
        for pack in layers.packs:
            if const.TIMEZONES not in pack:
                continue
            key = layers.add(pack, const.TIMEZONES)
            countries = set(layers.column(key, "country") or ())
            if pack.name == world_pack:
                self.world = key
            elif len(countries) == 1:
                self.country_keys.append((key, next(iter(countries))))
            else:
                self.geometric.append(key)
        self._candidates = {}

    def __bool__(self):
        return bool(self.world or self.country_keys or self.geometric)

    # -- tables ---------------------------------------------------------------------------------

    @cached_property
    def _world_units(self):
        """Per countries row and admin1 row, the world feature of that unit (-1: none); shapes as
        (feature, countries row, admin1 row or -1); the one zone of each one-zone country ("")."""
        admin = self.admin
        c_row = (
            {cid: i for i, cid in enumerate(admin.countries.column("id"))}
            if admin.countries is not None
            else {}
        )
        a_row = admin.admin1_row_of_id
        country = np.full(len(c_row), -1, dtype=np.int64)
        admin1 = np.full(len(a_row), -1, dtype=np.int64)
        shapes, split = [], np.zeros(len(c_row), dtype=bool)
        col = {f: self.layers.column(self.world, f) for f in ("basis", "unit", "within", "country", "zones")}
        for f, basis in enumerate(col["basis"]):
            ci = c_row.get(col["country"][f], -1)
            if basis == "country" and ci >= 0 and country[ci] < 0:
                country[ci] = f
            elif basis == "admin1" and col["unit"][f] in a_row:
                admin1[a_row[col["unit"][f]]] = f
            elif basis == "shape" and ci >= 0:
                shapes.append((f, ci, a_row.get(col["within"][f], -1)))
            if ci >= 0 and (basis != "country" or col["zones"][f]):
                split[ci] = True
        zone = self.layers.column(self.world, "zone")
        sole = np.array(
            [zone[f] if f >= 0 and not split[i] else "" for i, f in enumerate(country)], dtype=object
        )
        return country, admin1, shapes, sole

    @cached_property
    def _city_zones(self):
        cities = self.layers.layer(const.CITIES)
        if cities is None or "timezone" not in cities.fields:
            return None
        return np.asarray(cities.column("timezone"), dtype=object)

    # -- the vectorised answer ------------------------------------------------------------------

    def answer(self, a, lat, lon):
        n = len(lat)
        a["tz_zone"], a["tz_source"] = np.full(n, None, dtype=object), np.full(n, None, dtype=object)
        todo = a["cidx"] >= 0
        if self.world is not None:
            self._worldview(a, todo)
        if self.country_keys:
            iso2, agreed = self.admin.iso2_of_view(a), self.admin.undisputed(a)
            for key, country in self.country_keys:
                pts = np.flatnonzero(todo & agreed & (iso2 == country.removeprefix("iso:")))
                if len(pts):
                    feature = np.atleast_1d(self.layers.layer(key).query(lat[pts], lon[pts]))
                    self._fill(a, key, pts, feature, const.POLYGON, lat, lon, todo)
        if self.world is not None:
            pts = np.flatnonzero(todo)
            feature = self._world_features(a, pts, lat, lon)
            offshore = a["cmode"][pts] == const.OFFSHORE
            for rule, sel in ((const.POLYGON, ~offshore), (const.OFFSHORE, offshore)):
                self._fill(a, self.world, pts[sel], feature[sel], rule, lat, lon, todo)
        for key in self.geometric:
            pts = np.flatnonzero(todo)
            self._fill(
                a, key, pts, self._first_of_country(key, a, pts, lat, lon), const.POLYGON, lat, lon, todo
            )

    def _worldview(self, a, todo):
        sole = self._world_units[3]
        view, cidx = a["view"], a["cidx"]
        moved = np.flatnonzero(todo & (view >= 0) & (view != cidx))
        zones = sole[view[moved]]
        moved, zones = moved[zones != ""], zones[zones != ""]
        a["tz_zone"][moved] = zones
        a["tz_source"][moved] = self.layers.source(self.world, const.WORLDVIEW)
        todo[moved] = False

    def _world_features(self, a, pts, lat, lon):
        """The world feature of each point's own unit: a shape of its country containing it, else its
        admin1 unit's, else its country's; -1 if none."""
        country, admin1, shapes, _ = self._world_units
        cidx, aidx = a["cidx"][pts], a["aidx"][pts]
        out = np.full(len(pts), -1, dtype=np.int64)
        layer = self.layers.layer(self.world)
        for f, ci, ai in shapes:
            sel = np.flatnonzero((out < 0) & (cidx == ci) & ((aidx == ai) if ai >= 0 else True))
            if len(sel):
                inside = np.atleast_1d(layer.contains(lat[pts[sel]], lon[pts[sel]], np.full(len(sel), f)))
                out[sel[inside]] = f
        own = (out < 0) & (aidx >= 0)
        if len(admin1) and own.any():
            safe = np.maximum(aidx, 0)
            mine = own & (self.admin.admin1_country[safe] == cidx) & (admin1[safe] >= 0)
            out[mine] = admin1[safe[mine]]
        rest = out < 0
        out[rest] = country[cidx[rest]] if len(country) else -1
        return out

    def _first_of_country(self, key, a, pts, lat, lon):
        """Per point, the first feature of layer `key` that contains it and belongs to its country."""
        out = np.full(len(pts), -1, dtype=np.int64)
        if not len(pts) or self.admin.countries is None:
            return out
        point, feature = self.layers.layer(key).query_every(lat[pts], lon[pts])
        own_id = np.asarray(self.admin.countries.column("id"), dtype=object)[a["cidx"][pts]]
        feature_country = np.asarray(self.layers.column(key, "country"), dtype=object)
        keep = feature_country[feature] == own_id[point]
        point, feature = point[keep], feature[keep]
        first = np.flatnonzero(np.diff(point, prepend=-1))  # sorted by point, then feature
        out[point[first]] = feature[first]
        return out

    def _fill(self, a, key, pts, feature, rule, lat, lon, todo):
        """Write the zones of `feature` (one per point, -1: none) where they have one."""
        hit = feature >= 0
        pts, feature = pts[hit], feature[hit]
        zone = np.asarray(self.layers.column(key, "zone"), dtype=object)[feature]
        zones = np.asarray(self.layers.column(key, "zones"), dtype=object)[feature]
        source = np.full(len(pts), self.layers.source(key, rule), dtype=object)
        for f in np.unique(feature[zones != ""]):
            sel = np.flatnonzero(feature == f)
            decided = self._split(key, int(f), lat[pts[sel]], lon[pts[sel]])
            ok = decided != None  # noqa: E711 - elementwise on an object array
            zone[sel[ok]] = decided[ok]
            source[sel[ok]] = self.layers.source(key, const.SPLIT)
        has = zone != ""
        a["tz_zone"][pts[has]], a["tz_source"][pts[has]] = zone[has], source[has]
        todo[pts[has]] = False

    def _split(self, key, f, plat, plon):
        """The zone of the nearest city inside feature f whose zone is one of its zones (None where
        no such city is within TZ_SEARCH_KM)."""
        index = self._candidates.get((key, f))
        if index is None:
            index = self._candidates[key, f] = self._candidate_index(key, f)
        out = np.full(len(plat), None, dtype=object)
        if index is None:
            return out
        rows, _ = index.nearest(plat, plon, 1, const.TZ_SEARCH_KM)
        found = rows[:, 0] >= 0
        out[found] = self._city_zones[rows[found, 0]]
        return out

    def _candidate_index(self, key, f):
        zones = self._city_zones
        if zones is None:
            return None
        cities, layer = self.layers.layer(const.CITIES), self.layers.layer(key)
        allowed = self.layers.column(key, "zones")[f].split("|")
        rows = np.flatnonzero(np.isin(zones, allowed))
        b = layer.bbox(f)
        south, west, north, east = b.south, b.west, b.north, b.east
        lat, lon = cities.lat[rows], cities.lon[rows]
        in_lon = (lon >= west) & (lon <= east) if west <= east else (lon >= west) | (lon <= east)
        rows = rows[(lat >= south) & (lat <= north) & in_lon]
        if len(rows):
            rows = rows[
                np.atleast_1d(layer.contains(cities.lat[rows], cities.lon[rows], np.full(len(rows), f)))
            ]
        return RowIndex(cities.lat, cities.lon, rows) if len(rows) else None
