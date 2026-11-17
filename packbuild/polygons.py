"""Projected polygon rings into placewise Features: simplify in metres, unproject, group holes.

Rings come as (n, 2) arrays of projected (x, y) metres, in the shapefile / Esri JSON convention:
outer rings clockwise, holes counter-clockwise. Simplifying before unprojecting means the tolerance
is a distance on the ground (Lambert conformal conic keeps scale within a few percent across
southern Canada), not a fraction of a degree that shrinks with latitude.

Each feature is simplified on its own (Douglas-Peucker), so the shared border of two neighbours
can differ by up to the tolerance: a sliver of that width may belong to both or to neither.
"""

import numpy as np

from placewise.model import Feature, Outline


def signed_area(ring):
    """Shoelace area of an (n, 2) ring; negative when it runs clockwise (x east, y north)."""
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def simplify_ring(ring, tolerance):
    """The ring without its closing vertex, simplified with Douglas-Peucker to `tolerance` (same
    units as the coordinates); None when it collapses below three vertices. tolerance <= 0 only
    drops the closing vertex."""
    pts = np.asarray(ring, dtype=np.float64)
    if len(pts) > 1 and np.array_equal(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    if tolerance <= 0:
        return pts
    # split the closed ring at its first vertex and the vertex farthest from it
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
    if far == 0:
        return None
    first = pts[: far + 1]
    second = np.vstack([pts[far:], pts[:1]])
    kept = np.vstack([first[_keep(first, tolerance)][:-1], second[_keep(second, tolerance)][:-1]])
    return kept if len(kept) >= 3 else None


def _keep(line, tolerance):
    """Douglas-Peucker on an open polyline: a mask of the vertices to keep (always both ends)."""
    keep = np.zeros(len(line), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        a, b, between = line[i], line[j], line[i + 1 : j]
        dx, dy = b - a
        length = np.hypot(dx, dy)
        if length == 0:
            dist = np.hypot(*(between - a).T)
        else:
            dist = np.abs(dx * (between[:, 1] - a[1]) - dy * (between[:, 0] - a[0])) / length
        k = int(np.argmax(dist))
        if dist[k] > tolerance:
            k += i + 1
            keep[k] = True
            stack += [(i, k), (k, j)]
    return keep


def to_feature(rings, tolerance, projection, fid):
    """A Feature (with id `fid`) from one record's projected rings. Rings smaller than the tolerance
    are dropped, with their holes; a feature that would vanish entirely keeps its largest ring as
    drawn, so every record still has a shape."""
    rings = [np.asarray(r, dtype=np.float64) for r in rings]
    rings = [r[:-1] if len(r) > 1 and np.array_equal(r[0], r[-1]) else r for r in rings]
    rings = [r for r in rings if len(r) >= 3]
    if not rings:
        raise ValueError(f"{fid}: no ring with three or more vertices")
    areas = [signed_area(r) for r in rings]
    outer = [i for i, a in enumerate(areas) if a < 0]
    if not outer:  # some writers ignore winding: every ring is a polygon of its own
        outer = list(range(len(rings)))
    holes = {i: [] for i in outer}
    lo = np.array([rings[o].min(axis=0) for o in outer])
    hi = np.array([rings[o].max(axis=0) for o in outer])
    for i, ring in enumerate(rings):
        if i in holes:
            continue
        p = ring[0]
        candidates = np.flatnonzero(np.all(lo <= p, axis=1) & np.all(p <= hi, axis=1))
        owner = next((outer[c] for c in candidates if _inside(rings[outer[c]], p)), None)
        if owner is not None:  # a hole outside every outer ring would add area under even-odd: drop it
            holes[owner].append(i)

    outlines = []
    for o in outer:
        shell = simplify_ring(rings[o], tolerance)
        if shell is None:
            continue
        kept = [h for h in (simplify_ring(rings[i], tolerance) for i in holes[o]) if h is not None]
        outlines.append(Outline(tuple(_latlon(r, projection) for r in (shell, *kept))))
    if not outlines:
        largest = max(outer, key=lambda i: abs(areas[i]))
        outlines.append(Outline((_latlon(rings[largest], projection),)))
    return Feature(tuple(outlines), {}, fid)


def _inside(ring, p):
    """Even-odd test of one point against one ring."""
    x, y = ring[:, 0], ring[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    crosses = (y > p[1]) != (yn > p[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        at = x + (p[1] - y) * (xn - x) / (yn - y)
    return bool(np.count_nonzero(crosses & (p[0] < at)) % 2)


def _latlon(ring, projection):
    lon, lat = projection.inverse(ring[:, 0], ring[:, 1])
    return tuple(zip(lat.tolist(), lon.tolist(), strict=True))
