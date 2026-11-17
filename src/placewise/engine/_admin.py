"""Country and admin1 for every point at once, the worldview mapping and disputed areas.

- country: the containing polygon; outside every polygon, the nearest country within
  TERRITORIAL_KM (12 nmi; Natural Earth's 1:10m coast misses some coastal points), rule "offshore".
  The polygon's country is then mapped through the worldview order.
- admin1: the containing polygon if it belongs to that country, else the nearest of that country's
  admin1 features within TERRITORIAL_KM ("nearest" on land, "offshore" at sea). Country packs may
  then correct it (placewise.engine.naming).
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as const
from placewise.model import Disputed

from ._index import best_per_query
from ._worldview import Worldviews


class Admin:
    def __init__(self, layers):
        self.layers = layers
        self.countries = layers.layer(const.COUNTRIES)
        self.admin1 = layers.layer(const.ADMIN1)
        self._disputes = {}

    @cached_property
    def worldviews(self):
        return Worldviews(self.countries) if self.countries is not None else None

    # -- per-feature tables -----------------------------------------------------------------------

    @cached_property
    def admin1_country(self):
        """Per admin1 feature, the countries row of its unit (adm0_a3), or -1."""
        wv = self.worldviews
        if wv is None or "adm0_a3" not in self.admin1.fields:
            return np.full(self.admin1.count, -1, dtype=np.int64)
        return np.array([wv.row_of_adm0.get(c, -1) for c in self.admin1.column("adm0_a3")], dtype=np.int64)

    @cached_property
    def admin1_foreign(self):
        if self.worldviews is None:
            return np.full(self.admin1.count, -1, dtype=np.int64)
        return self.worldviews.foreign_rows(self.admin1)

    @cached_property
    def admin1_row_of_id(self):
        """{admin1 id: row}, for country packs whose states carry the same ids ("iso:US-CA")."""
        if self.admin1 is None:
            return {}
        return {pid: i for i, pid in enumerate(self.admin1.column("id"))}

    @cached_property
    def codes(self):
        """Country codes as small integers, shared by the cities' country column and claimants."""
        vocab = {}
        cities = self.layers.layer(const.CITIES)
        if cities is not None and "country" in cities.fields:
            for code in np.unique(cities.column("country")):
                vocab.setdefault(code, len(vocab))
        if self.worldviews is not None:
            for code in self.worldviews.code:
                vocab.setdefault(code, len(vocab))
        vocab.pop("", None)  # an unknown country matches nothing
        return vocab

    @cached_property
    def claimant_codes(self):
        """(countries, width) claimant code ints per polygon, padded with -1."""
        wv = self.worldviews
        rows = [
            [self.codes[wv.code[r]] for r in claim if wv.code[r] in self.codes] for claim in wv.claimant_rows
        ]
        width = max(map(len, rows), default=1)
        out = np.full((wv.n, width), -1, dtype=np.int64)
        for j, codes in enumerate(rows):
            out[j, : len(codes)] = codes
        return out

    @cached_property
    def country_code(self):
        """Code int of each countries row, -1 when unknown."""
        return np.array([self.codes.get(c, -1) for c in self.worldviews.code], dtype=np.int64)

    # -- the vectorised answer --------------------------------------------------------------------

    def answer(self, a, lat, lon, order):
        """Fill a["cidx", "cmode", "aidx", "amode", "view", "applied", "foreign"]."""
        n = len(lat)
        a["cidx"], a["cmode"] = np.full(n, -1, dtype=np.int64), np.full(n, "", dtype=object)
        if self.countries is not None:
            self._countries(a, lat, lon)
        self._admin1(a, lat, lon)
        land = a["cidx"] >= 0
        if self.worldviews is not None:
            rows, applied = self.worldviews.resolve(order)
            a["view"] = np.where(land, rows[np.maximum(a["cidx"], 0)], -1)
            a["applied"] = applied
        else:
            a["view"] = np.full(n, -1, dtype=np.int64)
        a["foreign"] = (
            np.where(a["aidx"] >= 0, self.admin1_foreign[np.maximum(a["aidx"], 0)], -1)
            if self.admin1 is not None
            else np.full(n, -1, dtype=np.int64)
        )

    def _countries(self, a, lat, lon):
        cidx = np.atleast_1d(self.countries.query(lat, lon)).astype(np.int64)
        a["cmode"][cidx >= 0] = const.POLYGON
        miss = np.flatnonzero(cidx < 0)
        if len(miss):
            q, f, d = self.countries.near_boundary(lat[miss], lon[miss], const.TERRITORIAL_KM)
            best = best_per_query(q, d, len(miss))
            hit = best >= 0
            cidx[miss[hit]] = f[best[hit]]
            a["cmode"][miss[hit]] = const.OFFSHORE
        a["cidx"] = cidx

    def _admin1(self, a, lat, lon):
        n = len(lat)
        admin1 = self.admin1
        a["aidx"], a["amode"] = np.full(n, -1, dtype=np.int64), np.full(n, "", dtype=object)
        cidx = a["cidx"]
        if admin1 is None or not admin1.count:
            return
        owner = self.admin1_country
        has_own = np.zeros(max(len(a["cmode"]), 1), dtype=bool)
        if self.worldviews is not None:
            has_own = np.bincount(owner[owner >= 0], minlength=self.worldviews.n) > 0
        aidx = np.atleast_1d(admin1.query(lat, lon)).astype(np.int64)
        land = cidx >= 0
        unrestricted = (
            ~has_own[np.maximum(cidx, 0)] if self.worldviews is not None else np.ones(n, dtype=bool)
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

    def allowed(self, a, pts):
        """(len(pts), width) country code ints a city may have for each point, -1 padded; a row of
        -1 only means the country is unknown and any city may serve."""
        if self.worldviews is None:
            return np.full((len(pts), 1), -1, dtype=np.int64)
        base = self.claimant_codes[a["cidx"][pts]]
        view, foreign = a["view"][pts], a["foreign"][pts]
        extra = np.column_stack(
            [
                np.where(view >= 0, self.country_code[np.maximum(view, 0)], -1),
                np.where(foreign >= 0, self.country_code[np.maximum(foreign, 0)], -1),
            ]
        )
        return np.concatenate([base, extra], axis=1)

    def undisputed(self, a):
        """Per point: on land whose data agrees (no disputed polygon, no admin1 of another country)."""
        cidx = a["cidx"]
        if self.worldviews is None:
            return cidx >= 0
        return (cidx >= 0) & ~self.worldviews.disputed[np.maximum(cidx, 0)] & (a["foreign"] < 0)

    def iso2_of_view(self, a):
        """Per point, the ISO alpha-2 code of the country reported (after the worldview), or ""."""
        if self.worldviews is None:
            return np.full(len(a["view"]), "", dtype=object)
        iso2 = np.array([*self.worldviews.iso2, ""], dtype=object)
        return iso2[np.where(a["view"] >= 0, a["view"], len(iso2) - 1)]

    def disputed(self, ci, ai, foreign, applied, locked):
        """Disputed for a point in polygon ci (and admin1 ai), or None when the data agrees."""
        key = (ci, ai if foreign >= 0 else -1, applied[ci] if applied else None, locked)
        if key in self._disputes:
            return self._disputes[key]
        wv = self.worldviews
        out = None
        if wv is not None and (wv.disputed[ci] or foreign >= 0):
            claimants = {wv.code[r] for r in wv.claimant_rows[ci]}
            if foreign >= 0:
                claimants.add(wv.code[foreign])
            name = wv.names[ci] if wv.disputed[ci] else self.layers.place(const.ADMIN1, ai).name
            out = Disputed(
                name=name, claimants=tuple(sorted(claimants)), administered_by=wv.code[ci],
                applied_view=applied[ci] if applied else const.DE_FACTO, views=wv.views(ci), locked=locked,
            )  # fmt: skip
        self._disputes[key] = out
        return out
