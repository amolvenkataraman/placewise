"""Named points that sit inside a country pack's polygons: CGNDB's populated places inside census
subdivisions (Lake Louise inside Improvement District No. 9, Scarborough inside Toronto).

A point layer with `name`, `generic` (the kind of place: "Hamlet", "Urban Community") and `scale`
(the map scale from which the name is shown: a prominence). Which point is inside which polygon is
asked once per point and cached, as for GeoNames cities (`_cities.Cities.inside`).
"""

import numpy as np

from placewise.constants import naming as const
from placewise.model import Place, Point

from .._layers import codes, source_of


def point_maker(kind):
    """A Place maker for a point layer of named places."""

    def make(get, layer, i):
        return Place(
            get("id"), get("name") or get("id"), kind, point=Point(float(layer.lat[i]), float(layer.lon[i])),
            codes=codes(get, "generic", "province"), source=source_of(layer),
        )  # fmt: skip

    return make


class NamedPoints:
    def __init__(self, layers, key, polygons):
        self.layers, self.key, self.polygons = layers, key, polygons
        self.layer = layers.layer(key)
        generic = np.asarray(self.layer.column("generic").tolist(), dtype=object)
        self._locality_ok = np.isin(generic, list(const.CGNDB_LOCALITY_TERMS))
        self._sublocality_ok = np.isin(generic, list(const.CGNDB_SUBLOCALITY_TERMS))
        scale = np.asarray(self.layer.column("scale"), dtype=np.float64)
        self._radius = np.full(len(scale), const.CGNDB_SUBLOCALITY_KM[-1][1])
        for at_least, km in reversed(const.CGNDB_SUBLOCALITY_KM):
            self._radius[scale >= at_least] = km
        self._inside = np.full(self.layer.count, -2, dtype=np.int64)

    def inside(self, rows):
        """The polygon (row of `polygons`) each point row lies in, -1 for none."""
        rows = np.asarray(rows, dtype=np.int64)
        todo = np.unique(rows[self._inside[rows] == -2])
        if len(todo):
            polygons = self.layers.layer(self.polygons)
            self._inside[todo] = polygons.query(self.layer.lat[todo], self.layer.lon[todo])
        return self._inside[rows]

    def _candidates(self, lat, lon, feature, ok, max_km):
        """(rows, km, usable) of the k nearest points within max_km: usable where `ok` for that
        point's kind and inside the query point's own `feature`."""
        k = min(const.CGNDB_CANDIDATES, max(self.layer.count, 1))
        rows, km = self.layer.nearest(lat, lon, k=k, max_km=max_km)
        rows, km = np.asarray(rows).reshape(len(lat), -1), np.asarray(km).reshape(len(lat), -1)
        safe = np.maximum(rows, 0)
        usable = (rows >= 0) & ok[safe] & (feature[:, None] >= 0)
        if usable.any():
            inside = np.full(rows.shape, -1, dtype=np.int64)
            inside[usable] = self.inside(safe[usable])
            usable &= inside == feature[:, None]
        return safe, km, usable

    def locality(self, lat, lon, feature):
        """Per query point, the nearest settlement (CGNDB_LOCALITY_TERMS) within
        CGNDB_LOCALITY_KM inside the point's `feature`; -1 for none."""
        out = np.full(len(lat), -1, dtype=np.int64)
        if not len(lat):
            return out
        rows, _, usable = self._candidates(lat, lon, feature, self._locality_ok, const.CGNDB_LOCALITY_KM)
        has = usable.any(axis=1)
        out[has] = rows[has, np.argmax(usable[has], axis=1)]  # nearest first
        return out

    def sublocality(self, lat, lon, feature, skip):
        """Per query point, the neighbourhood (CGNDB_SUBLOCALITY_TERMS) inside the point's
        `feature` whose reach (CGNDB_SUBLOCALITY_KM by its scale) the point is deepest inside:
        Scarborough's reaches 4 km, a street's few blocks 1.5 km. skip(i, name) -> True drops a
        name (the locality's own); -1 for none."""
        out = np.full(len(lat), -1, dtype=np.int64)
        if not len(lat):
            return out
        reach = self._radius.max(initial=0.0)
        rows, km, usable = self._candidates(lat, lon, feature, self._sublocality_ok, reach)
        depth = np.where(usable & (km <= self._radius[rows]), km / self._radius[rows], np.inf)
        names = self.layers.column(self.key, "name")
        for i in np.flatnonzero(np.isfinite(depth).any(axis=1)).tolist():
            for j in np.argsort(depth[i], kind="stable").tolist():
                if not np.isfinite(depth[i, j]):
                    break
                if not skip(i, names[rows[i, j]]):
                    out[i] = rows[i, j]
                    break
        return out
