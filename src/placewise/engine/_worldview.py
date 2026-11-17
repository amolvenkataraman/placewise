"""Worldviews: which country each point is reported as, under an ordered list of views.

Natural Earth's default polygons are drawn de facto (who administers the ground). Its countries
file carries, per view XX, a column `adm0_a3_xx` naming the admin-0 unit that view groups each
polygon into, and its disputed-areas file (the world pack's `worldviews` layer) does the same for
99 areas drawn over the countries (Aksai Chin, Crimea, Gilgit-Baltistan ...). Together they give
Natural Earth's point-of-view countries exactly. A worldview order such as ("IN", "de_facto") is
read left to right, per point:

- "de_facto": the country polygon's own country;
- "disputed": no country, if the point is in a disputed area; otherwise the next entry;
- a view code: the unit the view puts the point's disputed area in, else the unit it puts the
  country polygon in; if neither column has a usable value ("-99", a code that is no unit in the
  layer, or no column for that view: a warning lists the views the pack has), the next entry.

If nothing decides, the polygon's own country. On top of Natural Earth, the curated tables in
placewise.constants.worldviews apply: units that are nobody's country answer as the unit that holds
them (Siachen Glacier: India), views that merge units Natural Earth keeps apart (CN: Hong Kong
and Macau), admin1 per view for disputed areas, and per-view area names.

`disputed` is reported for points in a disputed area, not for a view's claim on a whole country
(one view puts all of mainland China in Taiwan), and not for areas held by
constants.worldviews.UNFLAGGED_HOLDERS. Packs without the worldviews layer fall back to whole
polygons: a polygon is disputed when the views disagree about it.
"""

import warnings
from collections import Counter
from functools import lru_cache

import numpy as np

from placewise.constants import lookup as const
from placewise.constants import worldviews as wv_const


class Worldviews:
    def __init__(self, countries, areas=None):
        self.n = countries.count
        fields = countries.fields

        def col(name):
            return countries.column(name) if name in fields else np.full(self.n, "", dtype=object)

        ids, adm0, iso2, iso3 = col("id"), col("adm0_a3"), col("iso2"), col("iso3")
        self.sovereign = col("sovereign")
        self.names = col("name")
        self.row_of_adm0 = {c: i for i, c in enumerate(adm0) if c}
        # units that are nobody's country answer as the unit holding them (Siachen Glacier: India)
        self.de_facto_row = np.arange(self.n, dtype=np.int64)
        for unit, holder in wv_const.DE_FACTO_UNITS.items():
            if unit in self.row_of_adm0 and holder in self.row_of_adm0:
                self.de_facto_row[self.row_of_adm0[unit]] = self.row_of_adm0[holder]
        # how a claimant is written: ISO alpha-2 where the unit has one, else its Natural Earth code
        own = [iso2[i] or adm0[i] or ids[i].partition(":")[2] for i in range(self.n)]
        self.code = [own[r] for r in self.de_facto_row]
        self.iso2 = list(iso2)
        self.holders = {self.row_of_adm0[u] for u in wv_const.UNFLAGGED_HOLDERS if u in self.row_of_adm0}
        # the unit that owns an ISO alpha-2 code ("iso:AU", not "ne:CSI" which shares it)
        self.row_of_iso2 = {}
        for i, code in enumerate(iso2):
            if code and (code not in self.row_of_iso2 or ids[i] == f"iso:{code}"):
                self.row_of_iso2[code] = i
        self.iso3_to_iso2 = {c3.upper(): c2.upper() for c3, c2 in zip(iso3, iso2, strict=True) if c3 and c2}
        prefix = const.VIEW_COLUMN.format(view="")
        self.columns = sorted(f[len(prefix) :] for f in fields if f.startswith(prefix))
        self.assign = {v: self.units(countries.column(prefix + v)) for v in self.columns}
        self.claimant_rows = []
        for j in range(self.n):
            rows = {int(self.de_facto_row[j])} | {int(a[j]) for a in self.assign.values() if a[j] >= 0}
            self.claimant_rows.append(tuple(sorted(rows, key=lambda r: self.code[r])))
        self.polygon_disputed = np.array([len(rows) > 1 for rows in self.claimant_rows], dtype=bool)
        self.resolving = {v: self.merged(v, a) for v, a in self.assign.items()}
        self.areas = _Areas(self, areas) if areas is not None and areas.count else None
        self.available = sorted({*self.columns, *(self.areas.assign if self.areas else ())})
        self._warned = set()

    def units(self, values):
        """Rows of the units named by a view column ("-99" or no such unit: -1), de facto mapped."""
        rows = np.array(
            [self.row_of_adm0.get(v, -1) if v and v != const.NO_VIEW else -1 for v in values], dtype=np.int64
        )
        return np.where(rows >= 0, self.de_facto_row[np.maximum(rows, 0)], -1)

    def merged(self, view, rows):
        """A view's rows with constants.worldviews.VIEW_UNITS applied (CN: Hong Kong -> China)."""
        out = rows.copy()
        for unit, into in wv_const.VIEW_UNITS.get(view.upper(), {}).items():
            if unit in self.row_of_adm0 and into in self.row_of_adm0:
                out[out == self.row_of_adm0[unit]] = self.row_of_adm0[into]
        return out

    # -- orders -----------------------------------------------------------------------------------

    def normalise(self, order):
        """A worldview order as a tuple: "de_facto" / "disputed" as is, view codes upper-case, ISO
        alpha-3 codes turned into the alpha-2 their column is named by ("ind" -> "IN"). A view
        the pack has no column for warns once, naming the views it has, and is skipped."""
        if isinstance(order, str):
            order = (order,)
        out = []
        for entry in order:
            text = str(entry).strip()
            low = text.lower()
            if low in (const.DE_FACTO, const.DISPUTED):
                out.append(low)
            elif len(low) == 3 and low not in self.available and text.upper() in self.iso3_to_iso2:
                out.append(self.iso3_to_iso2[text.upper()])
            else:
                out.append(text.upper())
        if not out:
            raise ValueError("a worldview order needs at least one entry")
        for view in out:
            special = view in (const.DE_FACTO, const.DISPUTED)
            if not special and view.lower() not in self.available and view not in self._warned:
                self._warned.add(view)
                known = ", ".join([const.DE_FACTO, const.DISPUTED, *(v.upper() for v in self.available)])
                warnings.warn(
                    f"worldview {view!r} is not in this pack and is skipped; available: {known}",
                    UserWarning,
                    stacklevel=4,
                )
        return tuple(out)

    @lru_cache(maxsize=32)  # noqa: B019 - one Worldviews per Geocoder, a handful of orders
    def resolve(self, order):
        """Per country polygon as a whole: (row it is reported as, -1 for none; the entry that
        decided). For points far offshore, which are in no disputed area."""
        rows = self.de_facto_row.copy()
        applied = [const.DE_FACTO] * self.n
        for j in range(self.n):
            for view in order:
                if view == const.DE_FACTO:
                    break
                if view == const.DISPUTED:
                    if self.areas is None and self.polygon_disputed[j]:
                        rows[j], applied[j] = -1, view
                        break
                    continue
                column = self.resolving.get(view.lower())
                if column is not None and column[j] >= 0:
                    rows[j], applied[j] = column[j], view
                    break
        return rows, tuple(applied)

    def answer(self, order, cidx, area):
        """Per point (country polygon cidx, disputed area or -1): (row reported, -1 for none;
        the order entry that decided, an object array)."""
        n = len(cidx)
        c, ar = np.maximum(cidx, 0), np.maximum(area, 0)
        rows = np.full(n, -1, dtype=np.int64)
        applied = np.full(n, const.DE_FACTO, dtype=object)
        todo = cidx >= 0
        for view in order:
            if view == const.DE_FACTO or not todo.any():
                break
            if view == const.DISPUTED:
                hit = todo & self.flagged(cidx, area)
                applied[hit] = view
                todo &= ~hit
                continue
            value = np.full(n, -1, dtype=np.int64)
            if self.areas is not None and view.lower() in self.areas.assign:
                value = np.where(area >= 0, self.areas.assign[view.lower()][ar], -1)
            column = self.resolving.get(view.lower())
            if column is not None:
                value = np.where(value >= 0, value, column[c])
            hit = todo & (value >= 0)
            rows[hit], applied[hit] = value[hit], view
            todo &= ~hit
        rows[todo] = self.de_facto_row[c[todo]]
        return rows, applied

    def flagged(self, cidx, area):
        """Per point: in a disputed area (or, without the worldviews layer, a disputed polygon)."""
        if self.areas is None:
            return (cidx >= 0) & self.polygon_disputed[np.maximum(cidx, 0)]
        return (cidx >= 0) & (area >= 0) & self.areas.flagged[np.maximum(area, 0)]

    # -- what a point's Disputed says -------------------------------------------------------------

    def dispute(self, ci, area, applied):
        """(name, claimant codes, administered_by, views) for a point in polygon ci and disputed
        area `area` (-1 for none) under entry `applied`, or None when it isn't flagged."""
        if self.areas is not None:
            a = self.areas
            if area < 0 or not a.flagged[area]:
                return None
            name = wv_const.VIEW_AREA_NAMES.get(applied, {}).get(a.names[area], a.names[area])
            holder = int(a.holder[area])
            by = self.code[holder] if holder >= 0 else self.code[ci]
            return name, {*a.claimants[area], by}, by, {const.DE_FACTO: by, **a.views[area]}
        if not self.polygon_disputed[ci]:
            return None
        return self.names[ci], {self.code[r] for r in self.claimant_rows[ci]}, self.code[ci], self.views(ci)

    def views(self, j):
        """{view: claimant code} for polygon j: "de_facto" plus every view that differs from it."""
        out = {const.DE_FACTO: self.code[j]}
        for view, column in self.assign.items():
            if column[j] >= 0 and column[j] != self.de_facto_row[j]:
                out[view.upper()] = self.code[int(column[j])]
        return out

    def admin1_rows(self, applied, row_of_id):
        """Per disputed area, the admin1 row constants.worldviews.VIEW_ADMIN1 gives it under the
        order entry `applied`, or -1; None when that entry has no table."""
        table = wv_const.VIEW_ADMIN1.get(applied, {})
        if self.areas is None or not table:
            return None
        return np.array([row_of_id.get(table.get(name, ""), -1) for name in self.areas.names], dtype=np.int64)

    def foreign_rows(self, admin1):
        """Per admin1 feature, the country row named by its ISO 3166-2 id prefix when that country
        has a different sovereign from the unit Natural Earth places the feature in (Crimea:
        "iso:UA-43" in the RUS unit), else -1. Prefixes of the same sovereign (NL-SX in Sint
        Maarten, US-PR in Puerto Rico) are ISO's own nesting, not a difference between sources."""
        out = np.full(admin1.count, -1, dtype=np.int64)
        if "adm0_a3" not in admin1.fields:
            return out
        for f, (fid, a3) in enumerate(zip(admin1.column("id"), admin1.column("adm0_a3"), strict=True)):
            if not fid.startswith("iso:"):
                continue
            prefix = fid[4:].partition("-")[0]
            home = self.row_of_adm0.get(a3, -1)
            other = self.row_of_iso2.get(prefix, -1)
            if home < 0 or other < 0 or self.iso2[home] == prefix:
                continue
            if not self.sovereign[home] or self.sovereign[home] != self.sovereign[other]:
                out[f] = other
        return out


class _Areas:
    """The worldviews layer's disputed areas: per area, its holder, each view's unit, claimants."""

    def __init__(self, wv, layer):
        prefix = const.VIEW_COLUMN.format(view="")
        self.names = [str(n) for n in layer.column("name")]
        views = sorted(f[len(prefix) :] for f in layer.fields if f.startswith(prefix))
        raw = {v: wv.units(layer.column(prefix + v)) for v in views}
        self.assign = {v: wv.merged(v, r) for v, r in raw.items()}
        self.holder = wv.units(layer.column("adm0_a3"))
        self.claimants, self.views = [], []
        for k in range(layer.count):
            if self.holder[k] < 0:  # a unit with no country polygon (Abkhazia): most views' unit
                votes = Counter(int(r[k]) for r in raw.values() if r[k] >= 0)
                self.holder[k] = votes.most_common(1)[0][0] if votes else -1
            own = int(self.holder[k])
            rows = {own} | {int(r[k]) for r in raw.values() if r[k] >= 0}
            self.claimants.append(tuple(sorted({wv.code[r] for r in rows if r >= 0})))
            codes = {const.DE_FACTO: wv.code[own]} if own >= 0 else {}
            codes.update({v.upper(): wv.code[int(r[k])] for v, r in raw.items() if r[k] >= 0 and r[k] != own})
            self.views.append(codes)
        pairs = zip(self.claimants, self.holder.tolist(), strict=True)
        self.flagged = np.array([len(c) > 1 and h not in wv.holders for c, h in pairs], dtype=bool)
