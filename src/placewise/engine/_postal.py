"""World postcodes: Result.postal outside the country packs, from the world-postal pack's `postal`
points (constants.postal; packbuild.sources.geonames_postal).

A point gets the code of the nearest postcode point of its own country (the one the worldview
reports) within that country's reach (`reach_km`, sized from how densely the country's points
lie); in a country with a single code, that code wherever the point is. The codes are points, not
areas, so the answer is always NEAR (rule "nearest"), at the distance to the code's point. Points
whose country pack already gave a postal area keep it, and disputed ground gets none, as country
packs' names don't apply there either.
"""

import numpy as np

from placewise.constants import postal as const
from placewise.geo import haversine
from placewise.model import Place, PlaceKind, Point
from placewise.packs import once

from ._layers import codes, source_of


class WorldPostal:
    """The `postal` point layer of the first pack that has one. Falsy when none has."""

    def __init__(self, packs, layers):
        self.layers, self.key = layers, None
        for pack in packs:
            layer = pack.layers.get(const.LAYER)
            if layer is not None and layer.kind == "point" and len(layer) and "reach_km" in layer.fields:
                self.key = layers.add(pack, const.LAYER, _place)
                break

    def __bool__(self):
        return self.key is not None

    @property
    def source(self):
        return self.layers.source(self.key, const.NEAREST)

    @once
    def _table(self):
        """(country values, country index per row, reach per row, {country index: its only code's row})."""
        layer = self.layers.layer(self.key)
        values, of_row = layer.distinct("country")
        of_row = np.asarray(of_row, dtype=np.int64)
        primary = ~np.asarray(layer.column("secondary"), dtype=bool)
        counts = np.bincount(of_row[primary], minlength=len(values))
        only = {int(c): int(np.flatnonzero(primary & (of_row == c))[0]) for c in np.flatnonzero(counts == 1)}
        reach = np.asarray(layer.column("reach_km"), dtype=np.float64)
        return [str(v) for v in values], of_row, reach, only

    def answer(self, lat, lon, iso2, todo):
        """(row, km) per point: the postcode row answering it and the distance to its point (-1 and
        inf where none, and wherever `todo` is false)."""
        n = len(lat)
        rows, kms = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
        values, of_row, reach, only = self._table
        index = {v: i for i, v in enumerate(values)}
        pts = np.flatnonzero(todo)
        want = np.array([index.get(c, -1) for c in iso2[pts].tolist()], dtype=np.int64)
        pts, want = pts[want >= 0], want[want >= 0]
        if not len(pts):
            return rows, kms
        layer = self.layers.layer(self.key)
        k = min(const.NEIGHBOURS, layer.count)
        idx, km = layer.nearest(lat[pts], lon[pts], k=k, max_km=float(reach.max()))
        idx, km = np.asarray(idx).reshape(len(pts), k), np.asarray(km, dtype=np.float64).reshape(len(pts), k)
        safe = np.maximum(idx, 0)
        ok = (idx >= 0) & (of_row[safe] == want[:, None]) & (km <= reach[safe])
        hit = ok.any(axis=1)
        first = np.argmax(ok, axis=1)  # candidates come nearest first
        rows[pts[hit]] = idx[hit, first[hit]]
        kms[pts[hit]] = km[hit, first[hit]]
        for j in np.flatnonzero(~hit).tolist():  # a country with one code: that code anywhere in it
            row = only.get(int(want[j]))
            if row is not None:
                i = pts[j]
                rows[i] = row
                kms[i] = float(haversine(lat[i], lon[i], layer.lat[row], layer.lon[row]))
        return rows, kms


def _place(get, layer, row):
    return Place(
        get("id"), get("name") or get("id"), PlaceKind.POSTAL_CODE,
        point=Point(float(layer.lat[row]), float(layer.lon[row])),
        codes=codes(get, "place", "country"), source=source_of(layer),
    )  # fmt: skip
