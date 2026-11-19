"""Parks and protected areas: the ones a point is inside (Result.within) and the ones near it.

Park packs (usa-parks, can-parks, world-parks: docs/parks.md) carry two kinds of layer:

- outlines: polygon layers named `parks*` (one per tier: parks_national, parks_state ...). A park
  may be several rows (parcels, zones) sharing its `park` id; it is one Place.
- points: `park_points`, parks known only by a point and `radius_km` (a circle of the park's
  area, or 0). They are never `within`, only `near` ("in the area of" at distance 0), because
  a circle is not the park's outline.

Rules (constants: placewise.constants.parks; distances: NearSettings.park_tier1..3):

- names: rows named only by a kind of land ("Open Space", "Unknown Park": GENERIC_NAMES) are never
  within or near; the build leaves them out, packs built before it still have them.
- within: every park whose outline contains the point, most significant first: lower tier first,
  then the smaller park (a preserve inside a national park comes before it).
- near: parks the point is not inside whose outline comes within their tier's near distance
  (tier 4, local parks, never: inside only); point parks whose circle does. Nearest first, at most
  MAX_NEAR, listed after the notable cities. The distance is to the outline (or the circle's
  edge, 0 inside it); outlines give no bearing.
- one park, two packs: a point park with the name or an alias (case, accents and spacing aside) of
  an outline park found for the same point is that park, drawn by an outline pack (world-parks has
  Europe's national parks, eur-parks their outlines), so only the outline answers.
"""

import numpy as np

from placewise.constants import parks as const
from placewise.constants.lookup import COMPASS_POINTS, POLYGON
from placewise.geo import compass, initial_bearing
from placewise.model import Nearby, Place, PlaceKind, Point, Relation

from ._layers import codes, source_of
from .naming.rules import fold

RADIUS = "radius"  # rule name in Result.sources: within a point park's circle plus its near distance


class Parks:
    """The park layers of a set of packs. Empty (falsy) when none has any."""

    def __init__(self, packs, layers, near_settings):
        near_km = {t: getattr(near_settings, f) for t, f in const.NEAR_SETTING.items()}
        self._near = np.zeros(max(const.TIERS) + 1)
        for tier, km in near_km.items():
            self._near[tier] = km
        self.layers = layers
        self.outlines, self.points = [], []
        self._layer_of = {}  # layer key -> layer
        for pack in packs:
            for name, layer in pack.layers.items():
                if layer.kind == "polygon" and name.startswith(const.POLYGON_PREFIX):
                    self.outlines.append(self._register(pack, name, layer, _outline_place))
                elif layer.kind == "point" and name == const.POINTS:
                    self.points.append(self._register(pack, name, layer, _point_place))

    def __bool__(self):
        return bool(self.outlines or self.points)

    def _register(self, pack, name, layer, maker):
        key = self.layers.add(pack, name, maker)
        self._layer_of[key] = layer
        tier = np.asarray(layer.column("tier"), dtype=np.int64)
        info = {
            "key": key,
            "layer": layer,
            "tier": tier,
            "near_km": self._near[np.clip(tier, 0, len(self._near) - 1)],
            "area": np.nan_to_num(np.asarray(layer.column("area_km2"), dtype=np.float64), nan=np.inf),
            "park": layer.column("park").tolist() if "park" in layer.fields else layer.column("id").tolist(),
            "named": _named(layer.column("name")),
        }
        if layer.kind == "point":
            info["radius"] = np.asarray(layer.column("radius_km"), dtype=np.float64)
        return info

    def answer(self, lat, lon, near):
        """Per point: (within Places, near Nearbys, {"within": source, "near": source})."""
        n = len(lat)
        inside = [{} for _ in range(n)]  # park id -> (tier, area, key, row)
        close = [{} for _ in range(n)]  # park id -> (km, tier, key, row, bearing, word)
        for o in self.outlines:
            p, f = o["layer"].query_every(lat, lon)
            keep = o["named"][f]
            p, f = p[keep], f[keep]
            tier, area, park = o["tier"], o["area"], o["park"]
            for q, row in zip(p.tolist(), f.tolist(), strict=True):
                inside[q].setdefault(park[row], (int(tier[row]), float(area[row]), o["key"], row))
            radius = float(o["near_km"].max()) if len(o["near_km"]) else 0.0
            if near and radius > 0:
                p, f, km = o["layer"].near_boundary(lat, lon, radius)
                keep = (km <= o["near_km"][f]) & o["named"][f]
                for q, row, d in zip(p[keep].tolist(), f[keep].tolist(), km[keep].tolist(), strict=True):
                    _closest(close[q], o["park"][row], (d, int(o["tier"][row]), o["key"], row, None, None))
        if near:
            drawn = {}  # query -> folded names of the outline parks found for it, when needed
            for pt in self.points:
                self._near_points(pt, lat, lon, close, lambda q: self._drawn(drawn, q, inside[q], close[q]))
        return [self._result(inside[i], close[i]) for i in range(n)]

    def _drawn(self, cache, q, inside, close):
        """The folded names and aliases of the outline parks inside or near which query q lies."""
        if q not in cache:
            rows = [(v[2], v[3]) for v in inside.values()]
            rows += [(v[2], v[3]) for v in close.values() if v[4] is None]  # outlines have no bearing
            names = set()
            for key, row in rows:
                layer = self._layer_of[key]
                aliases = layer.value("aliases", row) if "aliases" in layer.fields else ""
                names.update(_folded(n) for n in (layer.value("name", row), *(aliases or "").split("|")) if n)
            cache[q] = names
        return cache[q]

    def _near_points(self, pt, lat, lon, close, drawn):
        layer = pt["layer"]
        if not len(layer):
            return
        k = min(const.POINT_NEIGHBOURS, len(layer))
        reach = float((pt["radius"] + pt["near_km"]).max())
        idx, dist = layer.nearest(lat, lon, k=k, max_km=reach)
        idx, dist = idx.reshape(len(lat), k), dist.reshape(len(lat), k)
        q, j = np.nonzero(idx >= 0)
        rows, d = idx[q, j], dist[q, j]
        edge = np.maximum(d - pt["radius"][rows], 0.0)
        keep = (edge <= pt["near_km"][rows]) & pt["named"][rows]
        q, rows, edge = q[keep], rows[keep], edge[keep]
        if not len(q):
            return
        bearing = np.atleast_1d(initial_bearing(lat[q], lon[q], layer.lat[rows], layer.lon[rows]))
        words = np.atleast_1d(compass(bearing, COMPASS_POINTS))
        found = zip(q.tolist(), rows.tolist(), edge.tolist(), bearing.tolist(), words.tolist(), strict=True)
        for qi, row, km, b, w in found:
            if _folded(layer.value("name", row)) in drawn(qi):
                continue  # an outline pack draws this park
            _closest(close[qi], pt["park"][row], (km, int(pt["tier"][row]), pt["key"], row, b, w))

    def _result(self, inside, close):
        if not inside and not close:
            return (), (), {}
        place, sources = self.layers.place, {}
        ranked = sorted(inside.values(), key=lambda v: (v[0], v[1]))
        within = tuple(place(key, row) for _, _, key, row in ranked)
        if ranked:
            sources["within"] = self.layers.source(ranked[0][2], POLYGON)
        nearby = sorted((v for pid, v in close.items() if pid not in inside), key=lambda v: (v[0], v[1]))
        nearby = nearby[: const.MAX_NEAR]
        out = tuple(
            Nearby(place(key, row), Relation.NEAR, km, b, w if b is not None else None)
            for km, _, key, row, b, w in nearby
        )
        if out:
            first = nearby[0]
            sources["near"] = self.layers.source(first[2], POLYGON if first[4] is None else RADIUS)
        return within, out, sources


def generic_name(name):
    """Whether a park name only says what kind of land it is ("Open Space", "Unknown Park"):
    placewise.constants.parks.GENERIC_NAMES."""
    text = name if name.isascii() else fold(name)  # accents only matter outside ASCII
    return " ".join(text.split()).casefold() in const.GENERIC_NAMES


def label_park(within):
    """The park a label names (docs/naming.md): the most significant park the point is in, if it
    is national or state level and not a national forest or grassland; else None."""
    for park in within:
        if park.tier is None or park.tier > const.LABEL_MAX_TIER:
            return None  # within is most significant first: nothing later qualifies
        if park.codes.get("designation") not in const.LABEL_SKIP_DESIGNATIONS:
            return park
    return None


def _folded(name):
    return " ".join(fold(name or "").split())


def _named(names):
    """Per row: whether its name is a name, not generic (generic_name)."""
    names = names.tolist() if hasattr(names, "tolist") else list(names)
    return np.fromiter((not generic_name(n or "") for n in names), dtype=bool, count=len(names))


def _closest(found, pid, value):
    old = found.get(pid)
    if old is None or value[0] < old[0]:
        found[pid] = value


def _outline_place(get, layer, row):
    return Place(
        get("park") or get("id"), get("name") or get("id"), PlaceKind.PARK, bbox=layer.bbox(row),
        tier=int(layer.column("tier")[row]), codes=codes(get, "designation", "code", "wikidata"),
        aliases=_aliases(get("aliases")), source=source_of(layer),
    )  # fmt: skip


def _point_place(get, layer, row):
    return Place(
        get("id"), get("name") or get("id"), PlaceKind.PARK,
        point=Point(float(layer.lat[row]), float(layer.lon[row])), tier=int(layer.column("tier")[row]),
        codes=codes(get, "designation", "wikidata"), aliases=_aliases(get("aliases")),
        source=source_of(layer),
    )  # fmt: skip


def _aliases(text):
    return tuple(a for a in (text or "").split("|") if a)
