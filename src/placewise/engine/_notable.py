"""Notable places near a point (Result.near), from the world-notable pack's `notable` layer.

Each place reaches as far as its fame allows (constants.notable.NEAR_KM_BY_FAME: the best known
2 km, well known 1 km, the rest 300 m); fame is a percentile within the place's kind
(packbuild.notable). Of the places whose reach covers the point, the MAX_NEAR with the best
score, fame x (1 - distance / reach), are listed nearest first, after the cities and parks.
Airports are left out (Result.airport names the airport). The label never changes.

The layer is split by fame into one point index per reach, so a world-famous place 2 km away is
found however many minor ones stand closer.
"""

import numpy as np

from placewise.constants import notable as const
from placewise.constants.lookup import COMPASS_POINTS
from placewise.geo import compass, initial_bearing
from placewise.model import Nearby, Place, PlaceKind, Point, Relation
from placewise.packs import PointIndex

from ._layers import codes, source_of

RADIUS = "radius"  # rule name in Result.sources: within the reach its fame gives
_CODES = ("iata", "icao", "ipeds", "aishe", "station_code")


class Notable:
    """The `notable` layers of a set of packs. Empty (falsy) when none has one."""

    def __init__(self, packs, layers):
        self.layers = layers
        self.bands = []  # (key, layer, rows, PointIndex, reach km, fame)
        for pack in packs:
            layer = pack.layers.get(const.LAYER)
            if layer is None or layer.kind != "point" or not len(layer):
                continue
            key = layers.add(pack, const.LAYER, _place)
            fame = np.asarray(layer.column("fame"), dtype=np.float64)
            listed = ~np.isin(layer.column("kind"), list(const.NOT_NEAR))
            upper = np.inf
            for lowest, km in const.NEAR_KM_BY_FAME:
                rows = np.flatnonzero(listed & (fame >= lowest) & (fame < upper))
                upper = lowest
                if len(rows):
                    index = PointIndex(layer.lat[rows], layer.lon[rows])
                    self.bands.append((key, rows, index, km, fame[rows]))

    def __bool__(self):
        return bool(self.bands)

    def answer(self, lat, lon):
        """Per point: (Nearby, ...) nearest first, and the layer key of the first ("" if none)."""
        n = len(lat)
        found = [[] for _ in range(n)]  # (score, km, key, row, query index)
        for key, rows, index, km, fame in self.bands:
            k = min(const.NEIGHBOURS, len(rows))
            idx, dist = index.nearest(lat, lon, k=k, max_km=km)
            idx, dist = idx.reshape(n, k), dist.reshape(n, k)
            q, j = np.nonzero(idx >= 0)
            hit, d = idx[q, j], dist[q, j]
            score = fame[hit] * (1.0 - d / km)
            for qi, s, dk, row in zip(
                q.tolist(), score.tolist(), d.tolist(), rows[hit].tolist(), strict=True
            ):
                found[qi].append((s, dk, key, row))
        out = []
        place = self.layers.place
        for i in range(n):
            best = sorted(found[i], key=lambda v: (-v[0], v[1]))[: const.MAX_NEAR]
            if not best:
                out.append(((), ""))
                continue
            best.sort(key=lambda v: v[1])
            near = []
            for _, km, key, row in best:
                p = place(key, row)
                b = float(initial_bearing(lat[i], lon[i], p.point.lat, p.point.lon))
                near.append(Nearby(p, Relation.NEAR, km, b, str(compass(b, COMPASS_POINTS))))
            out.append((tuple(near), best[0][2]))
        return out


def _place(get, layer, row):
    found = {"kind": get("kind")}
    pid = get("id")
    if pid.startswith("wikidata:"):
        found["wikidata"] = pid[len("wikidata:") :]
    found.update(codes(get, *_CODES))
    return Place(
        pid, get("name") or pid, PlaceKind(const.KINDS.get(get("kind"), PlaceKind.LANDMARK.value)),
        point=Point(float(layer.lat[row]), float(layer.lon[row])), codes=found,
        aliases=tuple(a for a in (get("aliases") or "").split("|") if a), source=source_of(layer),
    )  # fmt: skip
