"""The Geocoder: a point in, the places a person would name out (placewise.model.Result).

Rules, in the order they run (constants in placewise.constants.lookup):

- country: the containing polygon; outside every polygon, the nearest country within
  TERRITORIAL_KM (12 nmi; Natural Earth's 1:10m coast misses some coastal points), with the rule
  "offshore" in Result.sources; beyond that none, and `water` names the country whose boundary is
  nearest (OFFSHORE) up to WATER_SEARCH_KM, with the exact distance and bearing to that boundary.
  The polygon's country is then mapped through the worldview order.
- admin1: the containing polygon if it belongs to that country, else the nearest of that country's
  admin1 features within TERRITORIAL_KM ("nearest" on land, "offshore" at sea).
- city (provisional until the naming phase brings municipal polygons): among GeoNames cities within
  CITY_RADIUS_KM, the best population**ALPHA / (km + D0), halved for a city in another admin1 and
  never a city of another country (a disputed area's claimants all count as its country).
- tz: the zone of the nearest city of the same country. An approximation: it can be wrong in sparse
  areas crossed by a zone line, until zone polygons exist.
- airport: the nearest within NearSettings.airport; AT within AIRPORT_AT_KM, else NEAR.
- near: up to NearSettings.max_near notable cities (NOTABLE_POPULATION+) within
  NearSettings.notable_rural, nearest first, across borders, without the chosen city.

`lookup_many` runs every spatial query for all points at once and then builds the Results;
`lookup` is `lookup_many` with one point, so the two always agree.
"""

import inspect
from functools import cached_property

import numpy as np

from placewise.config import effective_worldview
from placewise.constants import lookup as const
from placewise.geo import compass, initial_bearing
from placewise.model import Disputed, Nearby, Place, PlaceKind, Point, Relation, Result, Settings
from placewise.packs import Pack, open_pack

from ._index import RowIndex, best_per_query
from ._worldview import Worldviews


class Geocoder:
    """Reverse geocoder over one or more packs. For each layer it needs (countries, admin1, cities,
    airports) it reads the first pack that has it; a missing layer leaves its fields empty.

    packs: opened Pack objects or pack directories; default: the "world" pack from the store
    (downloaded on first use unless settings.data.offline). overrides: any object with
    `apply(result, lat, lon) -> Result`, applied last to every answer."""

    def __init__(self, packs=None, settings=None, store=None, overrides=None):
        self.settings = settings or Settings()
        if packs is None:
            if store is None:
                from placewise.store import Store

                store = Store(settings=self.settings.data)
            packs = [store.ensure(const.DEFAULT_PACK)]
        self.packs = [p if isinstance(p, Pack) else open_pack(p) for p in packs]
        if not self.packs:
            raise ValueError("a Geocoder needs at least one pack")
        self.overrides = overrides
        # placewise.overrides' engine takes relabel=; a plain `apply(result, lat, lon)` hook works too
        self._overrides_relabel = overrides is not None and _accepts(overrides.apply, "relabel")
        self._layers = {}
        for name in (const.COUNTRIES, const.ADMIN1, const.CITIES, const.AIRPORTS):
            pack = next((p for p in self.packs if name in p), None)
            if pack is not None:
                self._layers[name] = (pack, pack[name])
        self.data_version = "+".join(f"{p.name}-{p.version}" for p in self.packs)
        self._places = {name: {} for name in self._layers}
        self._columns = {}
        self._disputes = {}

    def __repr__(self):
        return f"<Geocoder {self.data_version}>"

    # -- public API -------------------------------------------------------------------------------

    def lookup(self, lat, lon, *, worldview=None, near=True):
        """The Result for one point (WGS84 degrees)."""
        return self.lookup_many([lat], [lon], worldview=worldview, near=near)[0]

    def lookup_many(self, lats, lons, *, worldview=None, near=True):
        """Results for many points, one per point, in order. Vectorised: much faster per point."""
        lat = np.asarray(lats, dtype=np.float64).ravel()
        lon = np.asarray(lons, dtype=np.float64).ravel()
        if lat.shape != lon.shape:
            raise ValueError(f"{len(lat)} latitudes but {len(lon)} longitudes")
        bad = ~(np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180))
        if bad.any():
            i = int(np.flatnonzero(bad)[0])
            raise ValueError(f"point {i} ({lat[i]}, {lon[i]}) is not a valid WGS84 latitude/longitude")
        order, locked = self._order(worldview)
        if not len(lat):
            return []
        a = self._answer(lat, lon, order, near)
        results = self._build(lat, lon, a, order, locked)
        if self.overrides is not None:
            apply = self.overrides.apply
            extra = {"relabel": self._relabel} if self._overrides_relabel else {}
            results = [
                apply(r, x, y, **extra) for r, x, y in zip(results, lat.tolist(), lon.tolist(), strict=True)
            ]
        return results

    # -- worldview --------------------------------------------------------------------------------

    def _order(self, worldview):
        """(order, locked): the request's spelling normalised ("xa", "XAA" -> "XA"), then the
        operator lock applied by placewise.config.effective_worldview, as the server does."""
        norm = self._worldviews.normalise if self._worldviews is not None else _plain_order
        requested = norm(worldview) if worldview is not None else None
        order, locked = effective_worldview(self.settings, requested)
        return norm(order), locked

    @cached_property
    def _worldviews(self):
        layer = self._layer(const.COUNTRIES)
        return Worldviews(layer) if layer is not None else None

    def _near_km(self, kind):
        """How far `near` / `airport` search for a kind: the settings, unless an override Tune rule
        for the whole kind sets near_km (per-place near_km can only narrow; the engine applies it)."""
        default = (
            self.settings.near.airport if kind == PlaceKind.AIRPORT else self.settings.near.notable_rural
        )
        tuning = getattr(self.overrides, "tuning", None)
        if tuning is None:
            return default
        return tuning(kind=kind).get("near_km", default)

    def _relabel(self, result):
        """The label recomposed from a Result's fields, for the override engine after a rename."""
        if result.country is None and result.admin1 is None:
            return result.label  # offshore labels name a reference place, not the result's fields
        return self._label(result.country, result.admin1, result.locality, result.airport, result.water)

    # -- layers and lazily built indexes ---------------------------------------------------------

    def _layer(self, name):
        entry = self._layers.get(name)
        return entry[1] if entry else None

    def _source(self, name, rule):
        return f"{self._layers[name][0].name}/{name}:{rule}"

    @cached_property
    def _admin1_country(self):
        """Per admin1 feature, the countries row of its unit (adm0_a3), or -1."""
        admin1, wv = self._layer(const.ADMIN1), self._worldviews
        if wv is None or "adm0_a3" not in admin1.fields:
            return np.full(admin1.count, -1, dtype=np.int64)
        return np.array([wv.row_of_adm0.get(c, -1) for c in admin1.column("adm0_a3")], dtype=np.int64)

    @cached_property
    def _admin1_foreign(self):
        admin1 = self._layer(const.ADMIN1)
        if self._worldviews is None:
            return np.full(admin1.count, -1, dtype=np.int64)
        return self._worldviews.foreign_rows(admin1)

    @cached_property
    def _codes(self):
        """Country codes as small integers, shared by the cities' country column and claimants."""
        vocab = {}
        cities = self._layer(const.CITIES)
        if cities is not None and "country" in cities.fields:
            for code in np.unique(cities.column("country")):
                vocab.setdefault(code, len(vocab))
        if self._worldviews is not None:
            for code in self._worldviews.code:
                vocab.setdefault(code, len(vocab))
        vocab.pop("", None)  # an unknown country matches nothing
        return vocab

    @cached_property
    def _claimant_codes(self):
        """(countries, width) claimant code ints per polygon, padded with -1."""
        wv = self._worldviews
        rows = [
            [self._codes[wv.code[r]] for r in claim if wv.code[r] in self._codes]
            for claim in wv.claimant_rows
        ]
        width = max(map(len, rows), default=1)
        out = np.full((wv.n, width), -1, dtype=np.int64)
        for j, codes in enumerate(rows):
            out[j, : len(codes)] = codes
        return out

    @cached_property
    def _country_code(self):
        """Code int of each countries row, -1 when unknown."""
        return np.array([self._codes.get(c, -1) for c in self._worldviews.code], dtype=np.int64)

    @cached_property
    def _cities(self):
        layer = self._layer(const.CITIES)
        n = layer.count
        f = layer.fields
        pop = np.asarray(layer.column("population"), dtype=np.float64) if "population" in f else np.zeros(n)
        codes = layer.column("feature_code") if "feature_code" in f else np.full(n, "", dtype=object)
        country = layer.column("country") if "country" in f else np.full(n, "", dtype=object)
        unique, inverse = np.unique(country, return_inverse=True)
        lookup = np.array([self._codes.get(c, -2) for c in unique], dtype=np.int64)
        excluded = np.isin(codes, list(const.CITY_EXCLUDED_FEATURE_CODES))
        notable = np.flatnonzero((pop >= const.NOTABLE_POPULATION) & ~excluded)
        return {
            "layer": layer,
            "lat": layer.lat,
            "lon": layer.lon,
            "weight": np.maximum(pop, const.CITY_MIN_POPULATION) ** const.CITY_SCORE_ALPHA,
            "excluded": excluded,
            "country": lookup[inverse.ravel()] if n else np.zeros(0, dtype=np.int64),
            "tz": layer.column("timezone") if "timezone" in f else None,
            "notable": RowIndex(layer.lat, layer.lon, notable),
            "admin1": np.full(n, -2, dtype=np.int64),  # filled lazily: -2 unknown, -1 outside all
            "by_country": {},
        }

    def _city_admin1(self, rows):
        """The admin1 polygon each city point lies in (-1: none), computed once per city."""
        cache = self._cities["admin1"]
        admin1 = self._layer(const.ADMIN1)
        todo = np.unique(rows[cache[rows] == -2])
        if len(todo):
            cache[todo] = admin1.query(self._cities["lat"][todo], self._cities["lon"][todo]) if admin1 else -1
        return cache[rows]

    def _country_cities(self, code):
        """RowIndex over the cities of one country code (int), built on first use."""
        by = self._cities["by_country"]
        if code not in by:
            c = self._cities
            rows = np.flatnonzero(c["country"] == code)
            by[code] = RowIndex(c["lat"], c["lon"], rows, const.TZ_FALLBACK_CELL_DEG)
        return by[code]

    # -- the vectorised answer -------------------------------------------------------------------

    def _answer(self, lat, lon, order, near):
        n = len(lat)
        a = {"cidx": np.full(n, -1, dtype=np.int64), "cmode": np.full(n, "", dtype=object)}
        countries = self._layer(const.COUNTRIES)
        if countries is not None:
            self._countries(a, lat, lon)
        self._admin1(a, lat, lon)
        cidx = a["cidx"]
        land = cidx >= 0
        if self._worldviews is not None:
            rows, applied = self._worldviews.resolve(order)
            a["view"] = np.where(land, rows[np.maximum(cidx, 0)], -1)
            a["applied"] = applied
        else:
            a["view"] = np.full(n, -1, dtype=np.int64)
        a["foreign"] = (
            np.where(a["aidx"] >= 0, self._admin1_foreign[np.maximum(a["aidx"], 0)], -1)
            if (self._layer(const.ADMIN1) is not None)
            else np.full(n, -1, dtype=np.int64)
        )
        if self._layer(const.CITIES) is not None:
            self._city_and_tz(a, lat, lon, near)
        if self._layer(const.AIRPORTS) is not None:
            idx, dist = self._layer(const.AIRPORTS).nearest(
                lat, lon, k=1, max_km=self._near_km(PlaceKind.AIRPORT)
            )
            a["airport"], a["airport_km"] = np.atleast_1d(idx), np.atleast_1d(dist)
        far = np.flatnonzero(~land)
        a["water"], a["water_km"] = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
        a["water_at"] = np.full((n, 2), np.nan)  # the nearest point of that country's boundary
        if countries is not None and len(far):
            f, d, at_lat, at_lon = countries.nearest_boundary(lat[far], lon[far], const.WATER_SEARCH_KM)
            a["water"][far], a["water_km"][far] = f, d
            a["water_at"][far] = np.column_stack([at_lat, at_lon])
        return a

    def _countries(self, a, lat, lon):
        cidx = np.atleast_1d(self._layer(const.COUNTRIES).query(lat, lon)).astype(np.int64)
        a["cmode"][cidx >= 0] = const.POLYGON
        miss = np.flatnonzero(cidx < 0)
        if len(miss):
            q, f, d = self._layer(const.COUNTRIES).near_boundary(lat[miss], lon[miss], const.TERRITORIAL_KM)
            best = best_per_query(q, d, len(miss))
            hit = best >= 0
            cidx[miss[hit]] = f[best[hit]]
            a["cmode"][miss[hit]] = const.OFFSHORE
        a["cidx"] = cidx

    def _admin1(self, a, lat, lon):
        n = len(lat)
        admin1 = self._layer(const.ADMIN1)
        a["aidx"], a["amode"] = np.full(n, -1, dtype=np.int64), np.full(n, "", dtype=object)
        cidx = a["cidx"]
        if admin1 is None or not admin1.count:
            return
        owner = self._admin1_country
        has_own = np.zeros(max(len(a["cmode"]), 1), dtype=bool)
        if self._worldviews is not None:
            has_own = np.bincount(owner[owner >= 0], minlength=self._worldviews.n) > 0
        aidx = np.atleast_1d(admin1.query(lat, lon)).astype(np.int64)
        land = cidx >= 0
        unrestricted = (
            ~has_own[np.maximum(cidx, 0)] if self._worldviews is not None else np.ones(n, dtype=bool)
        )
        ok = (aidx >= 0) & land & ((owner[np.maximum(aidx, 0)] == cidx) | unrestricted)
        a["aidx"][ok] = aidx[ok]
        a["amode"][ok] = const.POLYGON
        need = np.flatnonzero(land & ~ok)
        if not len(need):
            return
        q, f, d = admin1.near_boundary(lat[need], lon[need], const.TERRITORIAL_KM)
        keep = (owner[f] == cidx[need[q]]) | unrestricted[need[q]]
        q, f, d = q[keep], f[keep], d[keep]
        best = best_per_query(q, d, len(need))
        hit = best >= 0
        pts = need[hit]
        a["aidx"][pts] = f[best[hit]]
        a["amode"][pts] = np.where(a["cmode"][pts] == const.POLYGON, const.NEAREST, const.OFFSHORE)

    def _allowed(self, a, pts):
        """(len(pts), width) country code ints a city may have for each point, -1 padded; a row of
        -1 only means the country is unknown and any city may serve."""
        if self._worldviews is None:
            return np.full((len(pts), 1), -1, dtype=np.int64)
        cidx = a["cidx"][pts]
        base = self._claimant_codes[cidx]
        view = a["view"][pts]
        foreign = a["foreign"][pts]
        extra = np.column_stack(
            [
                np.where(view >= 0, self._country_code[np.maximum(view, 0)], -1),
                np.where(foreign >= 0, self._country_code[np.maximum(foreign, 0)], -1),
            ]
        )
        return np.concatenate([base, extra], axis=1)

    def _city_and_tz(self, a, lat, lon, near):
        n = len(lat)
        c = self._cities
        cities = c["layer"]
        a["city"], a["city_km"] = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
        a["tz"] = np.full(n, -1, dtype=np.int64)
        land = np.flatnonzero(a["cidx"] >= 0)
        far = np.flatnonzero(a["cidx"] < 0)
        near_km = self._near_km(PlaceKind.LOCALITY)
        k_notable = max(const.NOTABLE_CANDIDATES, self.settings.near.max_near + 1)
        a["notable"], a["notable_km"] = (
            np.full((n, k_notable), -1, dtype=np.int64),
            np.full((n, k_notable), np.inf),
        )
        for pts, radius, restricted in (
            (land, const.CITY_RADIUS_KM, True),
            (far, const.OFFSHORE_LABEL_KM, False),
        ):
            if not len(pts):
                continue
            plat, plon = lat[pts], lon[pts]
            local, local_km = cities.nearest(plat, plon, k=const.CITY_CANDIDATES, max_km=radius)
            local, local_km = local.reshape(len(pts), -1), local_km.reshape(len(pts), -1)
            notable, notable_km = c["notable"].nearest(plat, plon, k_notable, max(radius, near_km))
            a["notable"][pts], a["notable_km"][pts] = notable, notable_km
            idx = np.concatenate([local, notable], axis=1)
            km = np.concatenate([local_km, notable_km], axis=1)
            allowed = self._allowed(a, pts) if restricted else None
            admin1 = a["aidx"][pts] if restricted else None
            city, city_km = self._choose_city(idx, km, radius, allowed, admin1)
            a["city"][pts], a["city_km"][pts] = city, city_km
            if restricted and c["tz"] is not None:
                a["tz"][pts] = self._tz_city(plat, plon, local, local_km, allowed)
        if not near:
            a["notable"][:] = -1

    def _choose_city(self, idx, km, radius, allowed, admin1):
        """The provisional city score, per row of candidates: (city row or -1, km)."""
        c = self._cities
        safe = np.maximum(idx, 0)
        valid = (idx >= 0) & (km <= radius) & ~c["excluded"][safe]
        if allowed is not None:
            valid &= self._country_ok(c["country"][safe], allowed)
        score = c["weight"][safe] / (km + const.CITY_SCORE_D0_KM)
        # the admin1 preference can only change the winner where two or more cities compete
        contest = valid & (valid.sum(axis=1) > 1)[:, None]
        if admin1 is not None and contest.any():
            city_admin1 = np.full(idx.shape, -1, dtype=np.int64)
            city_admin1[contest] = self._city_admin1(safe[contest])
            other = (city_admin1 >= 0) & (admin1[:, None] >= 0) & (city_admin1 != admin1[:, None])
            score = np.where(other, score * const.CITY_OTHER_ADMIN1_FACTOR, score)
        score = np.where(valid, score, -np.inf)
        best = np.argmax(score, axis=1) if score.shape[1] else np.zeros(len(idx), dtype=np.int64)
        rows = np.arange(len(idx))
        found = np.isfinite(score[rows, best]) if score.shape[1] else np.zeros(len(idx), dtype=bool)
        return np.where(found, safe[rows, best], -1), np.where(found, km[rows, best], np.inf)

    @staticmethod
    def _country_ok(codes, allowed):
        match = (codes[:, :, None] == allowed[:, None, :]).any(axis=2)
        return match | (allowed < 0).all(axis=1)[:, None]

    def _tz_city(self, plat, plon, local, local_km, allowed):
        """Row of the nearest city in the point's country (any feature code), or -1. The first
        allowed city among a point's k nearest is its nearest allowed one, so the search widens
        only for points that have none, to each claimant country's own cities."""
        out, best_km = self._first_allowed(local, local_km, allowed)
        miss = np.flatnonzero(out < 0)
        # each (missed point, claimant code) once, grouped by code (ascending: on a tie in
        # distance the lower code's city stays)
        row, col = np.nonzero(allowed[miss] >= 0)
        pair = np.unique(allowed[miss][row, col] * len(plat) + miss[row])
        codes, pts_all = pair // len(plat), pair % len(plat)
        starts = np.flatnonzero(np.diff(codes, prepend=-1))
        for g0, g1 in zip(starts, np.append(starts[1:], len(pair)), strict=False):
            pts, cities = pts_all[g0:g1], self._country_cities(int(codes[g0]))
            idx, km = cities.nearest(plat[pts], plon[pts], 1, const.TZ_SEARCH_KM)
            better = km[:, 0] < best_km[pts]
            out[pts[better]], best_km[pts[better]] = idx[better, 0], km[better, 0]
        return out

    def _first_allowed(self, idx, km, allowed):
        """(row, km) of the first candidate per row whose country is allowed; -1 and inf if none."""
        safe = np.maximum(idx, 0)
        ok = (idx >= 0) & self._country_ok(self._cities["country"][safe], allowed)
        first = np.argmax(ok, axis=1)
        rows = np.arange(len(idx))
        found = ok[rows, first]
        return np.where(found, safe[rows, first], -1), np.where(found, km[rows, first], np.inf)

    # -- building Results ------------------------------------------------------------------------

    def _build(self, lat, lon, a, order, locked):
        n = len(lat)
        minus = np.full(n, -1, dtype=np.int64)
        city = a.get("city", minus)
        airport = a.get("airport", minus)
        # every bearing and compass word at once; then plain lists, which index faster than arrays
        air_deg, air_word = self._bearings(lat, lon, const.AIRPORTS, airport)
        water_deg, water_word = self._polygon_bearing(lat, lon, a)
        far_city = np.where(a["cidx"] < 0, city, -1)
        back_word = self._bearings(lat, lon, const.CITIES, far_city, reverse=True)[1]
        near_rows = self._near_rows(lat, lon, a, city)

        cidx, view, aidx, foreign = (a[k].tolist() for k in ("cidx", "view", "aidx", "foreign"))
        cmode, amode = a["cmode"].tolist(), a["amode"].tolist()
        city, city_km, far_city = (
            city.tolist(),
            a.get("city_km", np.full(n, np.inf)).tolist(),
            far_city.tolist(),
        )
        tz_row = a.get("tz", minus).tolist()
        airport, airport_km = airport.tolist(), a.get("airport_km", np.full(n, np.inf)).tolist()
        air_deg, air_word = air_deg.tolist(), air_word.tolist()
        water, water_km = a["water"].tolist(), a["water_km"].tolist()
        water_deg, water_word, back_word = water_deg.tolist(), water_word.tolist(), back_word.tolist()
        lats, lons = lat.tolist(), lon.tolist()
        tz_col = self._cities["tz"] if const.CITIES in self._layers else None
        applied = a.get("applied")
        view_rows = self._worldviews.resolve(order)[0].tolist() if self._worldviews is not None else None
        src = {
            (name, rule): self._source(name, rule)
            for name in self._layers
            for rule in (const.POLYGON, const.OFFSHORE, const.NEAREST, const.SCORE)
        }
        place = self._place
        # the place caches, read directly in the loop below (place() fills them on a miss)
        country_places, admin1_places, city_places = (
            self._places.get(k, {}) for k in (const.COUNTRIES, const.ADMIN1, const.CITIES)
        )
        results = []
        for i in range(n):
            ci, vi, ai = cidx[i], view[i], aidx[i]
            sources = {}
            country = admin1 = city_place = tz = air = water_near = disputed = None
            if vi >= 0:
                country = country_places.get(vi) or place(const.COUNTRIES, vi)
                sources["country"] = src[const.COUNTRIES, cmode[i]]
            if ai >= 0:
                admin1 = admin1_places.get(ai) or place(const.ADMIN1, ai)
                sources["admin1"] = src[const.ADMIN1, amode[i]]
            if ci >= 0:
                disputed = self._disputed(ci, ai, foreign[i], applied, locked)
                if city[i] >= 0:
                    city_place = city_places.get(city[i]) or place(const.CITIES, city[i])
                    sources["city"] = sources["locality"] = src[const.CITIES, const.SCORE]
                t = tz_row[i]
                if t >= 0 and tz_col[t]:
                    tz = tz_col[t]
                    sources["tz"] = src[const.CITIES, const.NEAREST]
            elif water[i] >= 0:
                w = view_rows[water[i]]
                water_near = Nearby(
                    place(const.COUNTRIES, w if w >= 0 else water[i]), Relation.OFFSHORE,
                    water_km[i], water_deg[i], water_word[i],
                )  # fmt: skip
                sources["water"] = src[const.COUNTRIES, const.NEAREST]
            if airport[i] >= 0:
                km = airport_km[i]
                rel = Relation.AT if km <= const.AIRPORT_AT_KM else Relation.NEAR
                air = Nearby(place(const.AIRPORTS, airport[i]), rel, km, air_deg[i], air_word[i])
                sources["airport"] = src[const.AIRPORTS, const.NEAREST]
            near = tuple(
                Nearby(place(const.CITIES, row), Relation.NEAR, km, deg, word)
                for row, km, deg, word in near_rows[i]
            )
            if near:
                sources["near"] = src[const.CITIES, const.NEAREST]
            if ci >= 0:
                label = self._label(country, admin1, city_place, air, water_near)
            elif far_city[i] >= 0:
                ref = place(const.CITIES, far_city[i]).name
                label = f"{const.OFFSHORE_LABEL}, {_km(city_km[i])} {back_word[i]} of {ref}"
            elif water_near is not None:
                word = _opposite(water_near.compass)
                label = (
                    f"{const.OFFSHORE_LABEL}, {_km(water_near.distance_km)} {word} of {water_near.place.name}"
                )
            else:
                label = const.OFFSHORE_LABEL
            results.append(
                Result(
                    lat=lats[i], lon=lons[i], label=label, country=country, admin1=admin1, city=city_place,
                    locality=city_place, tz=tz, near=near, airport=air, water=water_near, disputed=disputed,
                    sources=sources, data_version=self.data_version,
                )
            )  # fmt: skip
        return results

    def _near_rows(self, lat, lon, a, city):
        """Per point, [(city row, km, bearing, compass), ...] for `near`, nearest first."""
        n = len(lat)
        if "notable" not in a or not self.settings.near.max_near:
            return [()] * n
        notable = a["notable"].copy()
        notable[(notable == city[:, None]) | (a["notable_km"] > self._near_km(PlaceKind.LOCALITY))] = -1
        # keep the first max_near valid columns of each row
        rank = np.cumsum(notable >= 0, axis=1)
        notable[rank > self.settings.near.max_near] = -1
        q, j = np.nonzero(notable >= 0)
        rows = notable[q, j]
        deg, word = self._bearings(lat[q], lon[q], const.CITIES, rows)
        out = [[] for _ in range(n)]
        for qi, row, km, d, w in zip(q.tolist(), rows.tolist(), a["notable_km"][q, j].tolist(), deg.tolist(),
                                     word.tolist(), strict=True):  # fmt: skip
            out[qi].append((row, km, d, w))
        return out

    def _bearings(self, lat, lon, layer_name, rows, reverse=False):
        """(degrees, compass words) from each point to the point-layer row (or back with reverse);
        NaN and "" where the row is -1."""
        rows = np.asarray(rows)
        deg = np.full(len(rows), np.nan)
        words = np.full(len(rows), "", dtype=object)
        ok = np.flatnonzero(rows >= 0)
        layer = self._layer(layer_name)
        if len(ok) and layer is not None:
            plat, plon = layer.lat[rows[ok]], layer.lon[rows[ok]]
            if reverse:
                b = np.atleast_1d(initial_bearing(plat, plon, lat[ok], lon[ok]))
            else:
                b = np.atleast_1d(initial_bearing(lat[ok], lon[ok], plat, plon))
            deg[ok] = b
            words[ok] = np.atleast_1d(compass(b, const.COMPASS_POINTS))
        return deg, words

    def _polygon_bearing(self, lat, lon, a):
        """Bearing from far-offshore points to the nearest point of their `water` country's
        boundary."""
        n = len(lat)
        deg, words = np.full(n, np.nan), np.full(n, "", dtype=object)
        far = np.flatnonzero(a["water"] >= 0)
        if len(far):
            at = a["water_at"][far]
            b = np.atleast_1d(initial_bearing(lat[far], lon[far], at[:, 0], at[:, 1]))
            deg[far], words[far] = b, np.atleast_1d(compass(b, const.COMPASS_POINTS))
        return deg, words

    def _label(self, country, admin1, city, airport, water):
        template = self.settings.label.template
        if not template:
            # style "locality" and "city" agree until the naming phase separates them
            parts = []
            for p in (city, admin1, country):
                if p is not None and p.name and (not parts or parts[-1] != p.name):
                    parts.append(p.name)
            return ", ".join(parts)
        names = {
            "city": city.name if city else "",
            "locality": city.name if city else "",
            "admin1": admin1.name if admin1 else "",
            "country": country.name if country else "",
            "airport": airport.place.name if airport else "",
            "water": water.place.name if water else "",
        }
        text = template.format_map(_Blank(names))
        parts = [p.strip() for p in text.split(",")]
        return ", ".join(p for p in parts if p)

    # -- places ----------------------------------------------------------------------------------

    def _place(self, layer_name, i):
        cache = self._places[layer_name]
        place = cache.get(i)
        if place is None:
            place = cache[i] = self._make_place(layer_name, i)
        return place

    def _column(self, layer_name, field):
        key = (layer_name, field)
        if key not in self._columns:
            layer = self._layer(layer_name)
            self._columns[key] = layer.column(field).tolist() if field in layer.fields else None
        return self._columns[key]

    def _make_place(self, layer_name, i):
        layer = self._layer(layer_name)

        def get(field):
            values = self._column(layer_name, field)
            return values[i] if values is not None else ""

        def codes(*fields):
            return {f: get(f) for f in fields if get(f)}

        pid = get("id")
        name = get("name") or pid
        source = layer.sources[0] if layer.sources else None
        if layer_name == const.COUNTRIES:
            return Place(
                pid, name, PlaceKind.COUNTRY, bbox=layer.bbox(i), codes=codes("iso2", "iso3"), source=source
            )
        if layer_name == const.ADMIN1:
            found = {"iso": pid[4:]} if pid.startswith("iso:") else {}
            found.update(codes("country"))
            return Place(pid, name, PlaceKind.ADMIN1, bbox=layer.bbox(i), codes=found, source=source)
        point = Point(float(layer.lat[i]), float(layer.lon[i]))
        if layer_name == const.CITIES:
            return Place(pid, name, PlaceKind.LOCALITY, point=point, codes=codes("country"), source=source)
        found = codes("iata", "icao", "country", "region")
        return Place(pid, name, PlaceKind.AIRPORT, point=point, codes=found, source=source)

    def _disputed(self, ci, ai, foreign, applied, locked):
        """Disputed for a point in polygon ci (and admin1 ai), or None when the data agrees."""
        key = (ci, ai if foreign >= 0 else -1, applied[ci] if applied else None, locked)
        if key in self._disputes:
            return self._disputes[key]
        wv = self._worldviews
        out = None
        if wv is not None and (wv.disputed[ci] or foreign >= 0):
            claimants = {wv.code[r] for r in wv.claimant_rows[ci]}
            views = wv.views(ci)
            if foreign >= 0:
                claimants.add(wv.code[foreign])
            name = wv.names[ci] if wv.disputed[ci] else self._place(const.ADMIN1, ai).name
            out = Disputed(
                name=name, claimants=tuple(sorted(claimants)), administered_by=wv.code[ci],
                applied_view=applied[ci] if applied else const.DE_FACTO, views=views, locked=locked,
            )  # fmt: skip
        self._disputes[key] = out
        return out


def _accepts(func, name):
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


class _Blank(dict):
    def __missing__(self, key):
        return ""


def _plain_order(order):
    return (order,) if isinstance(order, str) else tuple(order)


def _km(km):
    return f"{km:.0f} km" if km >= 10 else f"{km:.1f} km"


_OPPOSITE = {"N": "S", "NE": "SW", "E": "W", "SE": "NW", "S": "N", "SW": "NE", "W": "E", "NW": "SE"}


def _opposite(word):
    return _OPPOSITE.get(word, word)
