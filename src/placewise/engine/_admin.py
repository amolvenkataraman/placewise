"""Country and admin1 for every point at once, the worldview mapping and disputed areas.

- country: the containing polygon; outside every polygon, the nearest country within
  TERRITORIAL_KM (12 nmi; Natural Earth's 1:10m coast misses some coastal points), rule "offshore".
  The point's disputed area (the world pack's worldviews layer; offshore, the nearest one of the
  same country within TERRITORIAL_KM) and the polygon are then mapped through the worldview order.
- admin1: the containing polygon if it belongs to that country, else the nearest of that country's
  admin1 features within TERRITORIAL_KM ("nearest" on land, "offshore" at sea); in a disputed area,
  the admin1 the view's table gives it (rule "worldview", placewise.constants.worldviews). Country
  packs may then correct it (placewise.engine.naming).
"""

from functools import cached_property

import numpy as np

from placewise.constants import lookup as const
from placewise.constants import worldviews as wv_const
from placewise.model import Disputed

from ._index import best_per_query
from ._worldview import Worldviews


class Admin:
    def __init__(self, layers):
        self.layers = layers
        self.countries = layers.layer(const.COUNTRIES)
        self.admin1 = layers.layer(const.ADMIN1)
        self._disputes = {}
        self._view_admin1 = {}
        self._flags = {}

    @cached_property
    def areas(self):
        """The disputed areas (the worldviews layer of the first pack that has one), or None."""
        pack = next((p for p in self.layers.packs if wv_const.WORLDVIEWS in p), None)
        return self.layers.layer(self.layers.add(pack, wv_const.WORLDVIEWS)) if pack is not None else None

    @cached_property
    def worldviews(self):
        return Worldviews(self.countries, self.areas) if self.countries is not None else None

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
    def admin1_unanswered(self):
        """Per admin1 feature: in a unit that is nobody's country (constants.worldviews.DE_FACTO_UNITS),
        so never reported as it stands."""
        units = {self.worldviews.row_of_adm0.get(u, -2) for u in wv_const.DE_FACTO_UNITS}
        return np.isin(self.admin1_country, list(units))

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
            for code in cities.distinct("country")[0]:
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
        """Fill a["cidx", "cmode", "area", "aidx", "amode", "view", "applied", "foreign"]: "area" is
        the disputed area or -1, "applied" the order entry that decided each point's country."""
        n = len(lat)
        a["cidx"], a["cmode"] = np.full(n, -1, dtype=np.int64), np.full(n, "", dtype=object)
        if self.countries is not None:
            self._countries(a, lat, lon)
        a["area"] = self._areas(a, lat, lon)
        if self.worldviews is not None:
            a["view"], a["applied"] = self.worldviews.answer(order, a["cidx"], a["area"])
        else:
            a["view"] = np.full(n, -1, dtype=np.int64)
            a["applied"] = np.full(n, const.DE_FACTO, dtype=object)
        self._admin1(a, lat, lon)
        self._admin1_of_view(a)
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

    def _areas(self, a, lat, lon):
        out = np.full(len(lat), -1, dtype=np.int64)
        wv = self.worldviews
        if wv is None or wv.areas is None:
            return out
        land = np.flatnonzero(a["cmode"] == const.POLYGON)
        if len(land):
            out[land] = np.atleast_1d(self.areas.query(lat[land], lon[land]))
        off = np.flatnonzero(a["cmode"] == const.OFFSHORE)
        if len(off):
            q, f, d = self.areas.near_boundary(lat[off], lon[off], const.TERRITORIAL_KM)
            keep = wv.areas.holder[f] == wv.de_facto_row[a["cidx"][off[q]]]
            best = best_per_query(q[keep], d[keep], len(off))
            hit = best >= 0
            out[off[hit]] = f[keep][best[hit]]
        return out

    def _admin1_of_view(self, a):
        """In a disputed area, the admin1 the deciding view's table gives it; admin1 features of
        units that are nobody's country are never reported as they stand."""
        if self.admin1 is None or self.worldviews is None:
            return
        aidx, area, applied = a["aidx"], a["area"], a["applied"]
        inside = np.flatnonzero(area >= 0)
        for entry in set(applied[inside].tolist()):
            if entry not in self._view_admin1:
                self._view_admin1[entry] = self.worldviews.admin1_rows(entry, self.admin1_row_of_id)
            rows = self._view_admin1[entry]
            if rows is None:
                continue
            pts = inside[applied[inside] == entry]
            found = rows[area[pts]]
            pts, found = pts[found >= 0], found[found >= 0]
            aidx[pts], a["amode"][pts] = found, wv_const.WORLDVIEW_RULE
        drop = (aidx >= 0) & self.admin1_unanswered[np.maximum(aidx, 0)]
        aidx[drop], a["amode"][drop] = -1, wv_const.WORLDVIEW_RULE  # a country pack may still fill it

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
        """Per point: on land where a country pack may name the country reported (after the
        worldview): no admin1 coded for another country under it (Crimea's iso:UA-43 in Russia)."""
        return (a["cidx"] >= 0) & (a["foreign"] < 0)

    def view_only(self, a, pts, rows, flags, view):
        """`rows` (features of a country pack's layer, per point of `pts`) with -1 where the
        feature is flagged in `flags` (a column: true for ground only `view` gives that country,
        such as the India pack's `india_view_only`) and the point's country wasn't decided by `view`."""
        if flags is None:
            return rows
        key = id(flags)
        if key not in self._flags or self._flags[key][0] is not flags:
            self._flags[key] = (flags, np.array([_truthy(v) for v in flags], dtype=bool))
        flagged = self._flags[key][1]
        hide = (rows >= 0) & flagged[np.maximum(rows, 0)] & (a["applied"][pts] != view)
        return np.where(hide, -1, rows)

    def iso2_of_view(self, a):
        """Per point, the ISO alpha-2 code of the country reported (after the worldview), or ""."""
        if self.worldviews is None:
            return np.full(len(a["view"]), "", dtype=object)
        iso2 = np.array([*self.worldviews.iso2, ""], dtype=object)
        return iso2[np.where(a["view"] >= 0, a["view"], len(iso2) - 1)]

    def disputed(self, a, i, locked):
        """Disputed for point i of the answer `a` (on land or in territorial waters), or None
        when it is in no disputed area and its admin1 is coded for its own country."""
        ci, area, ai, foreign = (int(a[k][i]) for k in ("cidx", "area", "aidx", "foreign"))
        applied = a["applied"][i]
        key = (ci, area, ai if foreign >= 0 else -1, applied, locked)
        if key in self._disputes:
            return self._disputes[key]
        wv = self.worldviews
        out = None
        found = wv.dispute(ci, area, applied) if wv is not None else None
        if found is None and wv is not None and foreign >= 0:
            legacy = wv.areas is None
            claimants = {wv.code[r] for r in wv.claimant_rows[ci]} if legacy else {wv.code[ci]}
            views = wv.views(ci) if legacy else {const.DE_FACTO: wv.code[ci]}
            found = (self.layers.place(const.ADMIN1, ai).name, claimants, wv.code[ci], views)
        if found is not None:
            name, claimants, by, views = found
            if foreign >= 0:
                claimants.add(wv.code[foreign])
            out = Disputed(
                name=name, claimants=tuple(sorted(claimants)), administered_by=by, applied_view=applied,
                views=views, locked=locked,
            )  # fmt: skip
        self._disputes[key] = out
        return out


def _truthy(value):
    """A pack column's flag: a non-zero number, or text other than "", "0", "false", "no"."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no")
    return bool(value)
