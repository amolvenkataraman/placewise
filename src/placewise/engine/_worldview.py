"""Worldviews: which country each country polygon is reported as, under an ordered list of views.

Natural Earth's default polygons are drawn de facto (who administers the ground). Its countries
file also carries, per view XX, a column `adm0_a3_xx` naming the admin-0 unit that view groups each
polygon into. A worldview order such as ("IN", "de_facto") is read left to right, per polygon:

- "de_facto": the polygon's own country;
- "disputed": no country, if the views disagree about this polygon; otherwise the next entry;
- a view code: the country its column names; if the pack has no such column, or the column has
  no usable value for this polygon ("-99", or a code that is no unit in the layer), the next entry.

If nothing decides, the polygon's own country. This module describes what the data records; it
takes no position on any claim.
"""

from functools import lru_cache

import numpy as np

from placewise.constants import lookup as const


class Worldviews:
    def __init__(self, countries):
        self.n = countries.count
        fields = countries.fields

        def col(name):
            return countries.column(name) if name in fields else np.full(self.n, "", dtype=object)

        ids, adm0, iso2, iso3 = col("id"), col("adm0_a3"), col("iso2"), col("iso3")
        self.sovereign = col("sovereign")
        self.names = col("name")
        # how a claimant is written: ISO alpha-2 where the unit has one, else its Natural Earth code
        self.code = [iso2[i] or adm0[i] or ids[i].partition(":")[2] for i in range(self.n)]
        self.iso2 = list(iso2)
        self.row_of_adm0 = {c: i for i, c in enumerate(adm0) if c}
        # the unit that owns an ISO alpha-2 code ("iso:AU", not "ne:CSI" which shares it)
        self.row_of_iso2 = {}
        for i, code in enumerate(iso2):
            if code and (code not in self.row_of_iso2 or ids[i] == f"iso:{code}"):
                self.row_of_iso2[code] = i
        self.iso3_to_iso2 = {c3.upper(): c2.upper() for c3, c2 in zip(iso3, iso2, strict=True) if c3 and c2}
        prefix = const.VIEW_COLUMN.format(view="")
        self.columns = sorted(f[len(prefix) :] for f in fields if f.startswith(prefix))
        self.assign = {}
        for view in self.columns:
            values = countries.column(const.VIEW_COLUMN.format(view=view))
            self.assign[view] = np.array(
                [self.row_of_adm0.get(v, -1) if v and v != const.NO_VIEW else -1 for v in values],
                dtype=np.int64,
            )
        self.claimant_rows = []
        for j in range(self.n):
            rows = {j} | {int(a[j]) for a in self.assign.values() if a[j] >= 0}
            self.claimant_rows.append(tuple(sorted(rows, key=lambda r: self.code[r])))
        self.disputed = np.array([len(rows) > 1 for rows in self.claimant_rows], dtype=bool)

    def normalise(self, order):
        """A worldview order as a tuple: "de_facto" / "disputed" as is, view codes upper-case, ISO
        alpha-3 codes turned into the alpha-2 their column is named by ("ind" -> "IN")."""
        if isinstance(order, str):
            order = (order,)
        out = []
        for entry in order:
            text = str(entry).strip()
            low = text.lower()
            if low in (const.DE_FACTO, const.DISPUTED):
                out.append(low)
            elif len(low) == 3 and low not in self.columns and text.upper() in self.iso3_to_iso2:
                out.append(self.iso3_to_iso2[text.upper()])
            else:
                out.append(text.upper())
        if not out:
            raise ValueError("a worldview order needs at least one entry")
        return tuple(out)

    @lru_cache(maxsize=32)  # noqa: B019 - one Worldviews per Geocoder, a handful of orders
    def resolve(self, order):
        """(row each polygon is reported as, -1 for none; the view entry that decided, per polygon)."""
        rows = np.arange(self.n, dtype=np.int64)
        applied = [const.DE_FACTO] * self.n
        for j in range(self.n):
            for view in order:
                if view == const.DE_FACTO:
                    break
                if view == const.DISPUTED:
                    if self.disputed[j]:
                        rows[j], applied[j] = -1, view
                        break
                    continue
                column = self.assign.get(view.lower())
                if column is not None and column[j] >= 0:
                    rows[j], applied[j] = column[j], view
                    break
        return rows, tuple(applied)

    def views(self, j):
        """{view: claimant code} for polygon j: "de_facto" plus every view that differs from it."""
        out = {const.DE_FACTO: self.code[j]}
        for view, column in self.assign.items():
            if column[j] >= 0 and column[j] != j:
                out[view.upper()] = self.code[int(column[j])]
        return out

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
