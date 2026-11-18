"""GeoNames cities: the provisional city score, the time zone and the notable cities nearby.

- city: among GeoNames cities within CITY_RADIUS_KM, the best population**ALPHA / (km + D0), halved
  for a city in another admin1 and never a city of another country (a disputed area's claimants
  all count as its country). Country packs name the locality and city by boundaries instead where
  they can (placewise.engine.naming); this score is the fallback and the rest of the world's answer.
- tz: where no timezones polygon answered (placewise.engine._timezones, a["tz_zone"]), the zone of
  the nearest city of the same country. An approximation: it can be wrong in sparse areas crossed
  by a zone line.
- notable: cities of NOTABLE_POPULATION+ near each point, for Result.near.
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as const

from ._index import RowIndex


class Cities:
    def __init__(self, layers, admin):
        self.layers = layers
        self.admin = admin
        self.layer = layers.layer(const.CITIES)
        self._by_country = {}
        self._inside = {}  # layer key -> per city row, the feature containing it (-2: not asked yet)

    @cached_property
    def table(self):
        layer = self.layer
        n, f = layer.count, layer.fields
        pop = np.asarray(layer.column("population"), dtype=np.float64) if "population" in f else np.zeros(n)
        codes = layer.column("feature_code") if "feature_code" in f else np.full(n, "", dtype=object)
        unique, inverse = _distinct(layer, "country")
        lookup = np.array([self.admin.codes.get(c, -2) for c in unique], dtype=np.int64)
        kinds, kind_of = _distinct(layer, "feature_code")
        excluded = np.isin(kinds, list(const.CITY_EXCLUDED_FEATURE_CODES))[kind_of]
        notable = np.flatnonzero((pop >= const.NOTABLE_POPULATION) & ~excluded)
        return {
            "population": pop,
            "weight": np.maximum(pop, const.CITY_MIN_POPULATION) ** const.CITY_SCORE_ALPHA,
            "feature_code": codes,
            "excluded": excluded,
            "country": lookup[inverse.ravel()] if n else np.zeros(0, dtype=np.int64),
            "tz": layer.column("timezone") if "timezone" in f else None,
            "notable": RowIndex(layer.lat, layer.lon, notable),
        }

    def inside(self, key, rows):
        """The feature of polygon layer `key` that each city row's point lies in (-1: none),
        asked once per city and layer."""
        layer = self.layers.layer(key)
        cache = self._inside.get(key)
        if cache is None:
            cache = self._inside[key] = np.full(self.layer.count, -2, dtype=np.int64)
        rows = np.asarray(rows, dtype=np.int64)
        todo = np.unique(rows[cache[rows] == -2])
        if len(todo):
            cache[todo] = layer.query(self.layer.lat[todo], self.layer.lon[todo])
        return cache[rows]

    def _country_cities(self, code):
        """RowIndex over the cities of one country code (int), built on first use."""
        if code not in self._by_country:
            rows = np.flatnonzero(self.table["country"] == code)
            self._by_country[code] = RowIndex(
                self.layer.lat, self.layer.lon, rows, const.TZ_FALLBACK_CELL_DEG
            )
        return self._by_country[code]

    # -- the vectorised answer --------------------------------------------------------------------

    def answer(self, a, lat, lon, near, near_km, k_notable):
        """Fill a["city", "city_km", "tz", "notable", "notable_km", "local", "local_km"]; local are
        each land point's CITY_CANDIDATES nearest cities (any feature code), for the naming rules."""
        n = len(lat)
        c = self.table
        k = const.CITY_CANDIDATES
        a["city"], a["city_km"] = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
        a["tz"] = np.full(n, -1, dtype=np.int64)
        a["local"], a["local_km"] = np.full((n, k), -1, dtype=np.int64), np.full((n, k), np.inf)
        a["notable"], a["notable_km"] = (
            np.full((n, k_notable), -1, dtype=np.int64),
            np.full((n, k_notable), np.inf),
        )
        land, far = np.flatnonzero(a["cidx"] >= 0), np.flatnonzero(a["cidx"] < 0)
        for pts, radius, restricted in (
            (land, const.CITY_RADIUS_KM, True),
            (far, const.OFFSHORE_LABEL_KM, False),
        ):
            if not len(pts):
                continue
            plat, plon = lat[pts], lon[pts]
            local, local_km = self.layer.nearest(plat, plon, k=k, max_km=radius)
            local, local_km = local.reshape(len(pts), -1), local_km.reshape(len(pts), -1)
            notable, notable_km = c["notable"].nearest(plat, plon, k_notable, max(radius, near_km))
            a["notable"][pts], a["notable_km"][pts] = notable, notable_km
            idx = np.concatenate([local, notable], axis=1)
            km = np.concatenate([local_km, notable_km], axis=1)
            allowed = self.admin.allowed(a, pts) if restricted else None
            admin1 = a["aidx"][pts] if restricted else None
            a["city"][pts], a["city_km"][pts] = self.choose(idx, km, radius, allowed, admin1)
            if restricted:
                a["local"][pts], a["local_km"][pts] = local, local_km
                need = _needs_tz(a, pts)
                if c["tz"] is not None and need.any():
                    a["tz"][pts[need]] = self._tz_city(
                        plat[need], plon[need], local[need], local_km[need], allowed[need]
                    )
        if not near:
            a["notable"][:] = -1

    def choose(self, idx, km, radius, allowed, admin1):
        """The provisional city score, per row of candidates: (city row or -1, km)."""
        c = self.table
        safe = np.maximum(idx, 0)
        valid = (idx >= 0) & (km <= radius) & ~c["excluded"][safe]
        if allowed is not None:
            valid &= _country_ok(c["country"][safe], allowed)
        score = c["weight"][safe] / (km + const.CITY_SCORE_D0_KM)
        # the admin1 preference can only change the winner where two or more cities compete
        contest = valid & (valid.sum(axis=1) > 1)[:, None]
        admin1_key = self.layers.world(const.ADMIN1)
        if admin1 is not None and admin1_key is not None and contest.any():
            city_admin1 = np.full(idx.shape, -1, dtype=np.int64)
            city_admin1[contest] = self.inside(admin1_key, safe[contest])
            other = (city_admin1 >= 0) & (admin1[:, None] >= 0) & (city_admin1 != admin1[:, None])
            score = np.where(other, score * const.CITY_OTHER_ADMIN1_FACTOR, score)
        score = np.where(valid, score, -np.inf)
        rows = np.arange(len(idx))
        if not score.shape[1]:
            return np.full(len(idx), -1, dtype=np.int64), np.full(len(idx), np.inf)
        best = np.argmax(score, axis=1)
        found = np.isfinite(score[rows, best])
        return np.where(found, safe[rows, best], -1), np.where(found, km[rows, best], np.inf)

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
        ok = (idx >= 0) & _country_ok(self.table["country"][safe], allowed)
        first = np.argmax(ok, axis=1)
        rows = np.arange(len(idx))
        found = ok[rows, first]
        return np.where(found, safe[rows, first], -1), np.where(found, km[rows, first], np.inf)


def _needs_tz(a, pts):
    """Which of the points no timezones polygon gave a zone (all of them without the layer)."""
    zone = a.get("tz_zone")
    return np.ones(len(pts), dtype=bool) if zone is None else zone[pts] == None  # noqa: E711


def _country_ok(codes, allowed):
    match = (codes[:, :, None] == allowed[:, None, :]).any(axis=2)
    return match | (allowed < 0).all(axis=1)[:, None]


def _distinct(layer, field):
    """np.unique(column, return_inverse=True) of a string column ("" for every row without it)."""
    if field in layer.fields:
        return layer.distinct(field)
    return np.array([""] * bool(layer.count), dtype=object), np.zeros(layer.count, dtype=np.int64)
