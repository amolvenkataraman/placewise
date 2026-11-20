"""Bounding boxes, point-in-polygon tests and areas.

A polygon is a list of rings, outer ring first and holes after it; each ring is a sequence of
(lat, lon) pairs, open or closed. Edges are great circles for `area`; `contains` treats lat/lon
as a plane, which is exact for the small, non-antimeridian shapes it is meant for.
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM

from ._arrays import as_floats


def bbox_around(lat, lon, distance_km, radius_km=MEAN_RADIUS_KM):
    """(south, west, north, east) of everything within distance_km of a point.

    Crossing the antimeridian gives west > east (the GeoJSON convention; `bbox_split` turns it
    into two boxes). Reaching a pole gives a box spanning every longitude."""
    r = distance_km / radius_km  # angular radius
    south, north = lat - math.degrees(r), lat + math.degrees(r)
    if north >= 90 or south <= -90:
        return (max(south, -90.0), -180.0, min(north, 90.0), 180.0)
    # widest longitude of a spherical cap, not r / cos(lat), which overshoots at high latitude
    ratio = math.sin(r) / math.cos(math.radians(lat))
    if ratio >= 1:
        return (south, -180.0, north, 180.0)
    dlon = math.degrees(math.asin(ratio))
    west, east = lon - dlon, lon + dlon
    if west < -180:
        west += 360
    if east > 180:
        east -= 360
    return (south, west, north, east)


def bbox_split(box):
    """A box as one or two boxes that don't cross the antimeridian."""
    south, west, north, east = box
    if west <= east:
        return [box]
    return [(south, west, north, 180.0), (south, -180.0, north, east)]


def bbox_contains(box, lats, lons):
    """Which points lie in the box (edges included); antimeridian-crossing boxes work."""
    south, west, north, east = box
    lat, lon = as_floats(lats, lons)
    in_lon = (lon >= west) & (lon <= east) if west <= east else (lon >= west) | (lon <= east)
    return _bools((lat >= south) & (lat <= north) & in_lon)


def contains(polygon, lats, lons):
    """Which points lie inside the polygon (holes excluded). Even-odd ray casting, vectorised over
    points; points exactly on an edge may land either way."""
    lat, lon = np.broadcast_arrays(*as_floats(lats, lons))
    inside = np.zeros(lat.shape, dtype=bool)
    for ring in polygon:
        ring = np.asarray(ring, dtype=np.float64)
        y1, x1 = ring[:, 0], ring[:, 1]
        y2, x2 = np.roll(y1, -1), np.roll(x1, -1)
        for ya, xa, yb, xb in zip(y1, x1, y2, x2, strict=True):
            if ya == yb:
                continue  # horizontal edges (and a closed ring's repeated vertex) never cross the ray
            crosses = (ya > lat) != (yb > lat)
            x_cross = xa + (lat - ya) * (xb - xa) / (yb - ya)
            inside ^= crosses & (lon < x_cross)
    return _bools(inside)


def area(polygon, radius_km=MEAN_RADIUS_KM):
    """Area in km² of a polygon with great-circle edges on a sphere: outer ring minus holes.
    Exact spherical excess (Van Oosterom & Strackee), so it holds for large shapes and poles."""
    outer, *holes = polygon
    excess = abs(_signed_excess(outer)) - sum(abs(_signed_excess(h)) for h in holes)
    return excess * radius_km**2


def nest(polygon):
    """The rings of an even-odd polygon (several polygons' rings together, as an Outline holds them)
    grouped into polygons: [[outer, hole, ...], ...] as ring indexes, outers in ring order. A ring
    held by an even number of the others is an outer ring; held by an odd number, a hole of the
    one ring that holds it one level up (an island in a lake in an island is an outer again). A
    ring counts as held when most of a sample of its vertices lies inside the other, so rings that
    touch at a vertex still nest."""
    rings = [open_ring(r) for r in polygon]
    boxes = np.array([[r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max()] for r in rings])
    holders = []
    for i, ring in enumerate(rings):
        sample = ring[np.unique(np.linspace(0, len(ring) - 1, min(len(ring), _NEST_SAMPLE)).astype(int))]
        around = np.all(boxes[:, :2] <= boxes[i, :2], axis=1) & np.all(boxes[:, 2:] >= boxes[i, 2:], axis=1)
        around[i] = False
        held = [j for j in np.flatnonzero(around).tolist() if _inside_ring(rings[j], sample).mean() > 0.5]
        holders.append(held)
    depth = [len(h) for h in holders]
    groups = {i: [i] for i in range(len(rings)) if depth[i] % 2 == 0}
    for i in range(len(rings)):
        if depth[i] % 2:
            owner = next((j for j in holders[i] if depth[j] == depth[i] - 1), None)
            if owner is not None:
                groups[owner].append(i)
    return list(groups.values())


def planar_signed_area(ring):
    """Shoelace area of a ring in the (lon, lat) plane, square degrees: positive when it runs
    counter-clockwise on a map (GeoJSON's outer rings), negative clockwise (its holes)."""
    r = open_ring(ring)
    x, y = r[:, 1], r[:, 0]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)) / 2


_NEST_SAMPLE = 9  # vertices of a ring tested against each ring whose box holds it


def open_ring(ring):
    """A ring as an (n, 2) float array without its closing repeat."""
    r = np.asarray(ring, dtype=np.float64).reshape(-1, 2)
    return r[:-1] if len(r) > 1 and np.array_equal(r[0], r[-1]) else r


def _inside_ring(ring, points):
    """Which of a few points lie inside one ring (even-odd), vectorised over the ring's edges."""
    y1, x1 = ring[:, 0], ring[:, 1]
    y2, x2 = np.roll(y1, -1), np.roll(x1, -1)
    lat, lon = points[:, :1], points[:, 1:]
    crosses = (y1 > lat) != (y2 > lat)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
    return np.count_nonzero(crosses & (lon < x_cross), axis=1) % 2 == 1


def _signed_excess(ring):
    """Signed solid angle (steradians) of a ring, summed over a fan of triangles from its first vertex."""
    ring = np.asarray(ring, dtype=np.float64)
    if len(ring) > 1 and np.array_equal(ring[0], ring[-1]):
        ring = ring[:-1]
    phi, lam = np.radians(ring[:, 0]), np.radians(ring[:, 1])
    v = np.column_stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)])
    a, b, c = v[0], v[1:-1], v[2:]
    triple = np.einsum("j,ij->i", a, np.cross(b, c))
    denominator = 1 + b @ a + np.einsum("ij,ij->i", b, c) + c @ a
    return float(np.sum(2 * np.arctan2(triple, denominator)))


def _bools(mask):
    return bool(mask) if mask.ndim == 0 else mask
