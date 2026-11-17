"""What every park source turns its records into: ParkRows, and from them the tier layers.

A park is one Place (its `park` id) drawn by one or more rows: PAD-US parcels, CPCAD zones. The
rows of a tier go into one polygon layer (`parks_national`, `parks_state`, `parks_regional`,
`parks_local`), each row with its own `id` (the park id, then `#2`, `#3` ... for further rows) and
the park's total area, so the engine can rank parks without adding parcels up at lookup time.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from placewise.constants.parks import LOCAL, NATIONAL, REGIONAL, STATE
from placewise.geo import from_web_mercator
from placewise.geo.shapes import area
from placewise.model import Feature, Outline

from ... import polygons
from ...layer import LayerData

LAYER_NAMES = {
    NATIONAL: "parks_national",
    STATE: "parks_state",
    REGIONAL: "parks_regional",
    LOCAL: "parks_local",
}
CELL_DEG = {NATIONAL: 1.0, STATE: 1.0, REGIONAL: 0.5, LOCAL: 0.25}  # grid cells: finer where parks are dense


@dataclass
class ParkRow:
    park: str  # the Place id: nps:YOSE, usfs:0505, cpcad:710300000, pad-us:ny:lp:central-park:dr5ru
    name: str
    tier: int
    designation: str
    feature: Feature  # lat/lon outlines
    source: str
    aliases: tuple[str, ...] = ()
    code: str = ""  # the publisher's own code: NPS unit code, USFS forest code
    area_km2: float = field(default=None)

    def __post_init__(self):
        if self.area_km2 is None:
            self.area_km2 = feature_area(self.feature)


class WebMercator:
    """EPSG:3857 as polygons.to_feature wants it: inverse(x, y) -> (lon, lat)."""

    @staticmethod
    def inverse(x, y):
        lat, lon = from_web_mercator(x, y)
        return np.asarray(lon), np.asarray(lat)


def feature_of(rings, projection, fid, tolerance=0.0):
    """The Feature for one record's projected rings (polygons.to_feature), with outlines that
    cross the antimeridian cut at ±180; None when no ring has three vertices."""
    try:
        feature = polygons.to_feature(rings, tolerance, _Wrapped(projection), fid)
    except ValueError:
        return None
    outlines = []
    for outline in feature.outlines:
        outlines += _split_antimeridian(outline)
    return Feature(tuple(outlines), {}, fid) if outlines else None


class _Wrapped:
    """A projection whose longitudes are wrapped into -180..180 (services write rings across the
    antimeridian with continuous coordinates, past 180); the jumps that leaves are cut below."""

    def __init__(self, projection):
        self.projection = projection

    def inverse(self, x, y):
        lon, lat = self.projection.inverse(x, y)
        lon = np.asarray(lon, dtype=np.float64)
        return np.where(np.abs(lon) > 180, (lon + 180) % 360 - 180, lon), lat


def feature_area(feature):
    """km² on the sphere (outer rings minus holes)."""
    return float(sum(area(o.rings) for o in feature.outlines))


def layers(rows):
    """The tier layers for ParkRows, national first; rows of one park keep their order."""
    by_tier = defaultdict(list)
    for row in rows:
        by_tier[row.tier].append(row)
    out = []
    for tier in sorted(by_tier):
        tier_rows = sorted(by_tier[tier], key=lambda r: r.park)
        total, seen = defaultdict(float), defaultdict(int)
        for r in tier_rows:
            total[r.park] += r.area_km2
        ids = []
        for r in tier_rows:
            seen[r.park] += 1
            ids.append(r.park if seen[r.park] == 1 else f"{r.park}#{seen[r.park]}")
        columns = {
            "id": ids,
            "park": [r.park for r in tier_rows],
            "name": [r.name for r in tier_rows],
            "tier": np.full(len(tier_rows), tier, dtype=np.uint8),
            "designation": [r.designation for r in tier_rows],
            "area_km2": np.array([total[r.park] for r in tier_rows], dtype=np.float32),
            "aliases": ["|".join(r.aliases) for r in tier_rows],
            "code": [r.code for r in tier_rows],
        }
        features = [Feature(r.feature.outlines, {}, i) for r, i in zip(tier_rows, ids, strict=True)]
        sources = tuple(dict.fromkeys(r.source for r in tier_rows))
        out.append(
            LayerData(
                LAYER_NAMES[tier], "polygon", columns, sources, features=features, cell_deg=CELL_DEG[tier]
            )
        )
    return out


def _split_antimeridian(outline):
    """[outline] unchanged, or its parts west and east of ±180 when a ring's edges jump across."""
    rings = [np.asarray(r, dtype=np.float64) for r in outline.rings]
    if not any(np.any(np.abs(np.diff(r[:, 1], append=r[:1, 1])) > 180) for r in rings):
        return [outline]
    parts = []
    for side in (-1, 1):
        kept = []
        for i, ring in enumerate(rings):
            lon = np.degrees(np.unwrap(np.radians(ring[:, 1])))
            lon = np.where(lon < 0, lon + 360, lon)  # continuous across 180, in 0..360
            clipped = _clip(np.column_stack([ring[:, 0], lon]), 180.0, keep_below=side < 0)
            if clipped is None:
                if i == 0:
                    break  # nothing of the shell on this side
                continue
            if side > 0:
                clipped[:, 1] -= 360
            kept.append(tuple(map(tuple, np.clip(clipped, [-90, -180], [90, 180]).tolist())))
        if kept:
            parts.append(Outline(tuple(kept)))
    return parts


def _clip(ring, x, keep_below):
    """Sutherland-Hodgman: the part of a ring (lat, lon) with lon <= x (or >= x); None if < 3."""
    lon = ring[:, 1]
    inside = lon <= x if keep_below else lon >= x
    out = []
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        ia, ib = inside[i], inside[(i + 1) % n]
        if ia:
            out.append(a)
        if ia != ib:
            t = (x - a[1]) / (b[1] - a[1])
            out.append(np.array([a[0] + t * (b[0] - a[0]), x]))
    if len(out) < 3:
        return None
    pts = np.asarray(out)
    return pts if len({tuple(p) for p in pts.tolist()}) >= 3 else None
