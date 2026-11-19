"""Time zones from the zones the packs give their admin units (packbuild/timezones.py,
docs/timezones.md).

For every point on land or within the territorial sea (country known), in this order:

1. worldview: where the worldview reports the point in another country than the one administering
   it, and that country has one zone, that zone (rule "worldview");
2. country packs (usa, can ...), on ground whose data agrees, in that pack's country: a shape of
   its `timezones` layer containing the point, else the `tz` of the finest unit the naming rules
   found it inside (a county, a census subdivision; rule "polygon"); a point inside none of those
   (a few by the shore), the first coarser unit containing it with a zone (division, province);
3. the world pack: the point's own unit, found through the admin answer already made (a shape of
   its country containing it, else its admin-1 unit's zone, else its country's), so the zone nests
   exactly in the country and admin-1 answers (rule "polygon", or "offshore" when the country is
   the one within TERRITORIAL_KM).

A unit whose zone lists several zones is split along a line the packs don't draw: the nearest
GeoNames city inside that unit whose zone is one of them decides (rule "split"), else its first
zone. A unit with no zone (tzdb records none) is left to the next rule. Points left without a zone
keep the nearest-city rule (placewise.engine._cities, "world/cities:nearest"); far at sea, none.
Result.sources names the pack's `timezones` ("world/timezones:polygon"), whichever layer holds the
zone.

Packs built before the zones moved onto the admin layers carry them as a `timezones` layer of
polygons copying each unit's outline; placewise.engine._timezones.legacy reads those.

Fills a["tz_zone"] (zone or None per point) and a["tz_source"] ("world/timezones:polygon" ...).
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.packs import once

from .._index import RowIndex
from . import legacy


class Timezones:
    def __init__(self, layers, admin, naming=None):
        self.layers, self.admin = layers, admin
        countries = layers.layer(const.COUNTRIES)
        world_pack = layers.world(const.COUNTRIES)
        world_pack = world_pack.split("/")[0] if world_pack else None
        self.columns = countries is not None and const.TZ_FIELD in countries.fields
        self.world_label = f"{world_pack}/{const.TIMEZONES}" if self.columns else None
        self.world, self.world_shapes, self.country_keys, self.geometric = None, None, [], []
        shapes = {}  # pack name -> key of its shapes-only timezones layer
        for pack in layers.packs:
            if const.TIMEZONES not in pack:
                continue
            key = layers.add(pack, const.TIMEZONES)
            if pack.name == world_pack:
                if self.columns:
                    self.world_shapes = key
                else:
                    self.world = key
            elif set(layers.column(key, "basis") or ()) <= {"shape"}:
                shapes[pack.name] = key
            elif len(countries_of := set(layers.column(key, "country") or ())) == 1:
                self.country_keys.append((key, next(iter(countries_of))))
            else:
                self.geometric.append(key)
        # country packs whose units carry their zone: (rule, shapes key or None, unit keys finest
        # first, label)
        self.units = []
        for rule in naming.rules if naming else ():
            units = rule.tz_layers()
            if units:
                pack = units[0].split("/")[0]
                self.units.append((rule, shapes.get(pack), units, f"{pack}/{const.TIMEZONES}"))
        self._candidates, self._zone_columns = {}, {}

    def __bool__(self):
        return bool(self.columns or self.world or self.country_keys or self.geometric or self.units)

    # -- tables ---------------------------------------------------------------------------------

    def zones(self, key):
        """(zone, zones) object arrays of a layer's rows: the default zone ("": none) and, for a unit
        split along a line no pack draws, its zones joined by TZ_SEPARATOR (else "")."""
        if key not in self._zone_columns:
            if "zone" in self.layers.layer(key).fields:  # a timezones layer: shapes, or the old units
                zone = np.asarray(self.layers.column(key, "zone"), dtype=object)
                every = np.asarray(self.layers.column(key, "zones"), dtype=object)
            else:
                tz = self.layers.column(key, const.TZ_FIELD)
                zone = np.array(
                    [z.split(const.TZ_SEPARATOR)[0] if z != const.TZ_NONE else "" for z in tz], dtype=object
                )
                every = np.array([z if const.TZ_SEPARATOR in z else "" for z in tz], dtype=object)
            self._zone_columns[key] = (zone, every)
        return self._zone_columns[key]

    @once
    def _world_units(self):
        """The world's units: "country" and "admin1" (per countries and admin1 row, the row of its
        zone in the layer holding it, -1: none), "shapes" ([(row, countries row, admin1 row or -1)]
        of the shapes layer), "sole" (each one-zone country's zone, else "") and "keys" (the layers
        holding the countries', admin-1 units' and shapes' zones)."""
        if not self.columns:
            return legacy.world_units(self, self.world)
        admin, layers = self.admin, self.layers
        c_key, a_key = layers.world(const.COUNTRIES), layers.world(const.ADMIN1)
        c_tz = layers.column(c_key, const.TZ_FIELD)
        c_row = {cid: i for i, cid in enumerate(admin.countries.column("id"))}
        a_tz = layers.column(a_key, const.TZ_FIELD) if a_key is not None else None
        admin1 = np.array([i if z else -1 for i, z in enumerate(a_tz or ())], dtype=np.int64)
        split = np.array([const.TZ_SEPARATOR in z for z in c_tz], dtype=bool)
        if len(admin1):
            owner = admin.admin1_country
            split[owner[(admin1 >= 0) & (owner >= 0)]] = True
        shapes = []
        if self.world_shapes is not None:
            s_key, a_row = self.world_shapes, admin.admin1_row_of_id
            within, country = (layers.column(s_key, f) for f in ("within", "country"))
            for f, (w, c) in enumerate(zip(within, country, strict=True)):
                ci = c_row.get(c, -1)
                if ci >= 0:
                    shapes.append((f, ci, a_row.get(w, -1)))
                    split[ci] = True
        sole = np.where(split, "", self.zones(c_key)[0]).astype(object)
        return {
            "country": np.arange(len(c_tz), dtype=np.int64), "admin1": admin1, "shapes": shapes,
            "sole": sole, "keys": (c_key, a_key, self.world_shapes),
        }  # fmt: skip

    @once
    def _city_zones(self):
        cities = self.layers.layer(const.CITIES)
        if cities is None or "timezone" not in cities.fields:
            return None
        return np.asarray(cities.column("timezone"), dtype=object)

    # -- the vectorised answer ------------------------------------------------------------------

    def answer(self, a, lat, lon, work=()):
        """`work`: the naming rules' (rule, points, state), whose units hold the country packs' zones."""
        n = len(lat)
        a["tz_zone"], a["tz_source"] = np.full(n, None, dtype=object), np.full(n, None, dtype=object)
        todo = a["cidx"] >= 0
        world = self.columns or self.world is not None
        if world:
            self._worldview(a, todo)
        if self.country_keys:
            legacy.country_layers(self, a, lat, lon, todo)
        self._country_units(a, lat, lon, todo, work)
        if world:
            pts = np.flatnonzero(todo)
            offshore = a["cmode"][pts] == const.OFFSHORE
            for key, sel, rows in self._world_features(a, pts, lat, lon):
                label = self.world_label or key
                for rule, part in ((const.POLYGON, ~offshore[sel]), (const.OFFSHORE, offshore[sel])):
                    self._fill(a, key, pts[sel][part], rows[part], rule, lat, lon, todo, label)
        for key in self.geometric:
            pts = np.flatnonzero(todo)
            rows = legacy.first_of_country(self, key, a, pts, lat, lon)
            self._fill(a, key, pts, rows, const.POLYGON, lat, lon, todo)

    def _worldview(self, a, todo):
        sole = self._world_units["sole"]
        view, cidx = a["view"], a["cidx"]
        moved = np.flatnonzero(todo & (view >= 0) & (view != cidx))
        zones = sole[view[moved]]
        moved, zones = moved[zones != ""], zones[zones != ""]
        a["tz_zone"][moved] = zones
        a["tz_source"][moved] = f"{self.world_label or self.world}:{const.WORLDVIEW}"
        todo[moved] = False

    def _country_units(self, a, lat, lon, todo, work):
        """Country packs whose units carry their zone: a shape containing the point, else the zone of
        the finest unit the naming rules found the point inside; a point inside none (the layers
        are simplified apart, so a few coastal points are in a province but no subdivision): the
        first coarser unit containing it that has a zone."""
        for rule, shapes, (finest, *coarser), label in self.units:
            for done_rule, pts, state in work:
                if done_rule is not rule:
                    continue
                keep = todo[pts]
                pts, rows = pts[keep], rule.tz_rows(state)[keep]
                if shapes is not None and len(pts):
                    found = np.atleast_1d(self.layers.layer(shapes).query(lat[pts], lon[pts]))
                    self._fill(a, shapes, pts, found, const.POLYGON, lat, lon, todo, label)
                    pts, rows = pts[found < 0], rows[found < 0]
                self._fill(a, finest, pts, rows, const.POLYGON, lat, lon, todo, label)
                outside = pts[rows < 0]
                for key in coarser:
                    outside = outside[todo[outside]]
                    if not len(outside):
                        break
                    found = np.atleast_1d(self.layers.layer(key).query(lat[outside], lon[outside]))
                    self._fill(a, key, outside, found, const.POLYGON, lat, lon, todo, label)

    def _world_features(self, a, pts, lat, lon):
        """[(key, selection of pts, rows)]: each point's own world unit as the row of its zone in the
        layer holding it (a shape of its country containing it, else its admin-1 unit's, else its
        country's; -1 if none)."""
        units = self._world_units
        country, admin1, (c_key, a_key, s_key) = units["country"], units["admin1"], units["keys"]
        cidx, aidx = a["cidx"][pts], a["aidx"][pts]
        out, which = np.full(len(pts), -1, dtype=np.int64), np.full(len(pts), 2, dtype=np.int8)
        if units["shapes"]:
            layer = self.layers.layer(s_key)
            for f, ci, ai in units["shapes"]:
                sel = np.flatnonzero((out < 0) & (cidx == ci) & ((aidx == ai) if ai >= 0 else True))
                if len(sel):
                    inside = np.atleast_1d(layer.contains(lat[pts[sel]], lon[pts[sel]], np.full(len(sel), f)))
                    out[sel[inside]], which[sel[inside]] = f, 0
        own = (out < 0) & (aidx >= 0)
        if len(admin1) and own.any():
            safe = np.maximum(aidx, 0)
            mine = own & (self.admin.admin1_country[safe] == cidx) & (admin1[safe] >= 0)
            out[mine], which[mine] = admin1[safe[mine]], 1
        rest = out < 0
        out[rest] = country[cidx[rest]] if len(country) else -1
        groups = ((s_key, which == 0), (a_key, which == 1), (c_key, which == 2))
        return [(key, np.flatnonzero(sel), out[sel]) for key, sel in groups if sel.any()]

    def _fill(self, a, key, pts, feature, rule, lat, lon, todo, label=None):
        """Write the zones of `feature` (rows of layer `key`, one per point, -1: none) where they
        have one; Result.sources names `label` (default: the layer itself)."""
        label = label or key
        hit = feature >= 0
        pts, feature = pts[hit], feature[hit]
        all_zone, all_zones = self.zones(key)
        zone, zones = all_zone[feature], all_zones[feature]
        source = np.full(len(pts), f"{label}:{rule}", dtype=object)
        for f in np.unique(feature[zones != ""]):
            sel = np.flatnonzero(feature == f)
            decided = self._split(key, int(f), lat[pts[sel]], lon[pts[sel]])
            ok = decided != None  # noqa: E711 - elementwise on an object array
            zone[sel[ok]] = decided[ok]
            source[sel[ok]] = f"{label}:{const.SPLIT}"
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
        allowed = self.zones(key)[1][f].split(const.TZ_SEPARATOR)
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
