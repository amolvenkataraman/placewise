"""Water shapes from (lon, lat) parts (packbuild.sources.water.shp) into placewise Features.

- Polygons are simplified with Douglas-Peucker in metres on a local equirectangular plane (x scaled
  by the cosine of the feature's mean latitude), so a tolerance means the same on the ground at
  any latitude; packbuild.polygons.to_feature does the grouping of holes and the simplification.
- Lines become zero-area polygons: each part traced out and back (v0 ... vn ... v1), so every
  edge is there twice, no point is ever inside (even-odd), and the boundary distance queries of a
  polygon layer (`near_boundary`, `nearest_boundary`) measure the distance to the line itself.
  This stands in for line layers until the pack format has them (docs/pack-format.md).
- An edge jumping more than 180° of longitude is refused by the pack writer. Natural Earth closes
  polar rings along the pole from -180 to 179.9999..., so such an edge whose ends both lie within
  POLE_SNAP_DEG of ±180 is snapped onto it; lines are split there instead.
"""

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo.shapes import area
from placewise.model import Feature, Outline

from ...polygons import to_feature

POLE_SNAP_DEG = 1e-3
_M_PER_DEG = MEAN_RADIUS_KM * 1000 * np.pi / 180


class _Local:
    """Equirectangular metres about latitude lat0; `inverse` undoes `forward`."""

    def __init__(self, lat0):
        self.kx = _M_PER_DEG * max(np.cos(np.radians(lat0)), 1e-6)

    def forward(self, lonlat):
        return np.column_stack([lonlat[:, 0] * self.kx, lonlat[:, 1] * _M_PER_DEG])

    def inverse(self, x, y):
        # clipped: the round trip can land a hair beyond ±180 / ±90
        return np.clip(np.asarray(x) / self.kx, -180, 180), np.clip(np.asarray(y) / _M_PER_DEG, -90, 90)


def snap_pole_edges(part):
    """The part with the ends of edges that jump across ±180 snapped onto it, when both ends lie
    within POLE_SNAP_DEG of it (a polar ring's closing edge); other jumps are left alone."""
    part = np.array(part, dtype=np.float64)
    lon = part[:, 0]
    nxt = np.roll(np.arange(len(lon)), -1)
    jump = np.abs(lon[nxt] - lon) > 180
    near = (180 - np.abs(lon)) <= POLE_SNAP_DEG
    for i in np.flatnonzero(jump & near & near[nxt]):
        for j in (i, nxt[i]):
            lon[j] = 180.0 if lon[j] > 0 else -180.0
    return part


def polygon_feature(parts, tolerance_m, fid):
    """A Feature from one record's rings (shapefile winding), simplified to tolerance_m metres."""
    parts = [snap_pole_edges(p) for p in parts if len(p) >= 3]
    lat0 = float(np.mean(np.concatenate([p[:, 1] for p in parts])))
    local = _Local(lat0)
    return to_feature([local.forward(p) for p in parts], tolerance_m, local, fid)


def line_feature(parts, fid):
    """A Feature from one record's lines (or several records' lines of one river): an outline
    per stretch, each a zero-area ring; split where a line crosses ±180, repeated vertices and
    single points dropped."""
    outlines = []
    for part in parts:
        part = np.asarray(part, dtype=np.float64)
        cuts = np.flatnonzero(np.abs(np.diff(part[:, 0])) > 180) + 1
        for piece in np.split(part, cuts):
            keep = np.ones(len(piece), dtype=bool)
            keep[1:] = np.any(np.diff(piece, axis=0) != 0, axis=1)  # no repeated vertices
            there = [(float(lat), float(lon)) for lon, lat in piece[keep]]
            distinct = list(dict.fromkeys(there))
            if len(distinct) < 2:
                continue
            if len(distinct) == 2:  # an outline needs three distinct corners: add the midpoint
                (y0, x0), (y1, x1) = distinct
                there = [distinct[0], ((y0 + y1) / 2, (x0 + x1) / 2), distinct[1]]
            outlines.append(Outline((tuple(there + there[-2:0:-1]),)))
    if not outlines:
        raise ValueError(f"{fid}: no line with two or more vertices")
    return Feature(tuple(outlines), {}, fid)


def area_km2(feature):
    """Area on the sphere: each outline's shell minus its holes."""
    return float(sum(area(outline.rings) for outline in feature.outlines))
