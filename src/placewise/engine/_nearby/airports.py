"""Which airport a point is at or near (Result.airport; docs/naming.md, "Airports").

1. AT: the nearest airport whose AT radius holds the point (constants.lookup.AIRPORT_AT_KM, by the
   airport's OurAirports `type`: 2.5 km large, 1 km medium, 0.5 km small). Any airport counts,
   with or without scheduled service: a point on Begumpet's apron is at Begumpet.
2. Otherwise NEAR: among the airports in reach (NearSettings.airport_large for large airports,
   NearSettings.airport for the others) with scheduled service (NearSettings.airport_scheduled),
   the one with the smallest distance times its size's weight (AIRPORT_WEIGHT): a large airport
   wins unless a smaller one is several times nearer, so a landing seen from Hyderabad's centre is
   HYD, not Begumpet (no scheduled service), and one on the Peninsula is SFO, not San Carlos.

Candidates per point: the AIRPORT_CANDIDATES nearest airports of any size within the smaller
reach, plus the nearest large airport within the larger one (its own index, so a cluster of small
fields can't hide it). Packs without a `type` column read every airport as AIRPORT_DEFAULT_TYPE;
without `scheduled`, every airport as served.
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.packs import PointIndex


class Airports:
    def __init__(self, layer):
        self.layer = layer
        n = len(layer)
        types = layer.column("type").tolist() if "type" in layer.fields else [const.AIRPORT_DEFAULT_TYPE] * n
        size = [t if t in const.AIRPORT_AT_KM else const.AIRPORT_DEFAULT_TYPE for t in types]
        self.large = np.array([s == const.LARGE_AIRPORT for s in size], dtype=bool)
        self.at_km = np.array([const.AIRPORT_AT_KM[s] for s in size], dtype=np.float64)
        self.weight = np.array([const.AIRPORT_WEIGHT[s] for s in size], dtype=np.float64)
        if "scheduled" in layer.fields:
            self.scheduled = np.asarray(layer.column("scheduled"), dtype=bool)
        else:
            self.scheduled = np.ones(n, dtype=bool)
        self._large_index = {}  # scheduled_only -> (rows, PointIndex) of the large airports

    def answer(self, a, lat, lon, reach_km, large_km, scheduled_only):
        """Fill a["airport"] (row or -1), a["airport_km"] and a["airport_at"] (bool) per point."""
        n = len(lat)
        large_km = max(large_km, reach_km)
        k = min(const.AIRPORT_CANDIDATES, len(self.layer))
        rows, km = self.layer.nearest(lat, lon, k=max(k, 1), max_km=reach_km)
        rows, km = rows.reshape(n, -1), km.reshape(n, -1)
        big_rows, big_km = self._nearest_large(lat, lon, large_km, scheduled_only)
        rows = np.concatenate([rows, big_rows[:, None]], axis=1)
        km = np.concatenate([km, big_km[:, None]], axis=1)
        have = rows >= 0
        safe = np.where(have, rows, 0)
        reach = np.where(self.large[safe], large_km, reach_km)
        have &= km <= reach
        at = have & (km <= np.minimum(self.at_km[safe], reach))
        served = have & (self.scheduled[safe] | (not scheduled_only))
        # AT beats everything (nearest first); then the smallest weighted distance (nearest on ties)
        cost = np.where(at, km - 1e6, np.where(served, km * self.weight[safe], np.inf))
        best = np.argmin(cost + np.where(have, km, 0.0) * 1e-9, axis=1)
        pick = np.arange(n)
        found = np.isfinite(cost[pick, best])
        a["airport"] = np.where(found, rows[pick, best], -1).astype(np.int64)
        a["airport_km"] = np.where(found, km[pick, best], np.inf)
        a["airport_at"] = found & at[pick, best]

    def _nearest_large(self, lat, lon, max_km, scheduled_only):
        rows, index = self._large(scheduled_only)
        n = len(lat)
        if index is None:
            return np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
        idx, km = index.nearest(lat, lon, k=1, max_km=max_km)
        idx, km = np.atleast_1d(idx), np.atleast_1d(km)
        return np.where(idx >= 0, rows[np.maximum(idx, 0)], -1), km

    def _large(self, scheduled_only):
        found = self._large_index.get(scheduled_only)
        if found is None:
            rows = np.flatnonzero(self.large & (self.scheduled | (not scheduled_only)))
            index = PointIndex(self.layer.lat[rows], self.layer.lon[rows]) if len(rows) else None
            found = self._large_index[scheduled_only] = (rows, index)
        return found
