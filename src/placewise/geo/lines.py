"""Paths as sequences of (lat, lon) points: simplification, the nearest point on a segment or a
polyline, and length.

Nearest points are exact on a sphere (segments are great-circle arcs). Simplification measures
its tolerance in metres in a local equirectangular projection around each segment or vertex,
which is accurate while segments stay well under ~100 km and away from the poles; it handles the
antimeridian.
"""

import heapq
import math

import numpy as np

from placewise.constants.distance import METRES_PER
from placewise.constants.earth import MEAN_RADIUS_KM

from ._arrays import as_floats, out, wrap_lon
from .distances import haversine

_METHODS = ("douglas_peucker", "visvalingam")


def simplify(points, tolerance_m, method="douglas_peucker"):
    """Indices (ascending int array) of the points to keep so the path stays within tolerance_m
    metres of the original. The first and last points are always kept. Indices rather than points
    so timestamps or other per-point data can be filtered alongside: `points[simplify(...)]`.

    "douglas_peucker" keeps any point farther than tolerance_m from the segment joining the points
    kept either side of it (distance to the segment, clamped at its ends, so back-tracking survives).
    "visvalingam" repeatedly drops the point whose triangle with its neighbours has the smallest
    area, while that area is at most tolerance_m² (m²); it favours smooth shapes over exact
    deviation bounds."""
    if method not in _METHODS:
        raise ValueError(f"method must be one of {_METHODS}, not {method!r}")
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    if n < 3:
        return np.arange(n)
    keep = (
        _douglas_peucker(pts, tolerance_m) if method == "douglas_peucker" else _visvalingam(pts, tolerance_m)
    )
    return np.flatnonzero(keep)


def nearest_point_on_segment(lat, lon, a, b, radius_km=MEAN_RADIUS_KM):
    """(lat, lon, distance_km, fraction) of the point on the great-circle arc a -> b nearest to
    (lat, lon). `fraction` is how far along the arc it lies (0 at a, 1 at b); points beyond the
    ends clamp to them. Broadcasts over query points; a and b are (lat, lon) pairs. Undefined for
    antipodal a and b, which have no unique arc."""
    lat, lon, dist, _, fraction = nearest_point_on_polyline(lat, lon, [a, b], radius_km)
    return lat, lon, dist, fraction


def nearest_point_on_polyline(lat, lon, points, radius_km=MEAN_RADIUS_KM):
    """(lat, lon, distance_km, segment_index, fraction) of the point on the path nearest to
    (lat, lon), with great-circle segments. `segment_index` i is the segment from points[i] to
    points[i + 1] and `fraction` the position along that segment; ties go to the earlier segment.
    Broadcasts over query points, comparing every query with every segment at once (memory grows
    with queries x segments)."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        raise ValueError("a polyline needs at least two points")
    lat, lon = np.broadcast_arrays(*as_floats(lat, lon))
    shape = lat.shape
    p = _unit(lat.ravel(), lon.ravel())[:, None, :]  # (queries, 1, 3)
    a, b = _unit(pts[:-1, 0], pts[:-1, 1]), _unit(pts[1:, 0], pts[1:, 1])  # (segments, 3)
    nearest, angle, fraction = _nearest_on_arcs(p, a, b)

    index = np.argmin(angle, axis=1)
    rows = np.arange(len(index))
    v = nearest[rows, index]
    near_lat = np.degrees(np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1]))).reshape(shape)
    near_lon = wrap_lon(np.degrees(np.arctan2(v[:, 1], v[:, 0]))).reshape(shape)
    dist = (radius_km * angle[rows, index]).reshape(shape)
    fraction = fraction[rows, index].reshape(shape)
    index = index.reshape(shape)
    return (
        out(near_lat),
        out(near_lon),
        out(dist),
        int(index) if index.ndim == 0 else index,
        out(fraction),
    )


def polyline_length(points, radius_km=MEAN_RADIUS_KM):
    """Length in km of a path: the sum of its great-circle (haversine) legs; 0 for under two points."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        return 0.0
    legs = haversine(pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1], radius_km)
    return float(np.sum(legs))


def _nearest_on_arcs(p, a, b):
    """Nearest points (q, s, 3), their angular distances (q, s) and fractions along each arc (q, s)
    for unit vectors p (q, 1, 3) against arcs a[i] -> b[i] (s, 3)."""
    normal = np.cross(a, b)
    normal_len = np.linalg.norm(normal, axis=-1, keepdims=True)
    degenerate = normal_len[..., 0] < 1e-15  # zero-length segment: just the point a
    n_hat = normal / np.where(degenerate[:, None], 1.0, normal_len)

    # foot of the perpendicular: drop p's component along the arc's pole and renormalise
    foot = p - np.sum(p * n_hat, axis=-1, keepdims=True) * n_hat
    foot_len = np.linalg.norm(foot, axis=-1, keepdims=True)
    # at the pole of the great circle every point of it is equally near; fall back to an endpoint
    foot_ok = foot_len[..., 0] > 1e-15
    foot = foot / np.where(foot_ok[..., None], foot_len, 1.0)
    # the foot is on the minor arc when it is a -> foot -> b in the arc's own direction of travel
    on_arc = (
        foot_ok
        & ~degenerate
        & (np.sum(np.cross(a, foot) * n_hat, axis=-1) >= 0)
        & (np.sum(np.cross(foot, b) * n_hat, axis=-1) >= 0)
    )
    nearer_b = np.sum(p * b, axis=-1) > np.sum(p * a, axis=-1)
    end = np.where((nearer_b & ~degenerate)[..., None], b, a)
    nearest = np.where(on_arc[..., None], foot, end)

    arc = _angle(a, b)
    along = np.where(on_arc, _angle(a, nearest), np.where(nearer_b, arc, 0.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        fraction = np.where(degenerate, 0.0, np.clip(along / arc, 0.0, 1.0))
    return nearest, _angle(p, nearest), fraction


def _angle(u, v):
    """Angle between unit vectors; atan2 stays accurate for tiny and near-180 deg angles."""
    return np.arctan2(np.linalg.norm(np.cross(u, v), axis=-1), np.sum(u * v, axis=-1))


def _unit(lat, lon):
    phi, lam = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)], axis=-1)


def _metres_xy(pts, lat0, lon0):
    """Points in metres east and north of (lat0, lon0) on the equirectangular plane tangent there."""
    m_per_deg = math.radians(MEAN_RADIUS_KM * METRES_PER["km"])
    x = wrap_lon(pts[..., 1] - lon0) * math.cos(math.radians(lat0)) * m_per_deg
    y = (pts[..., 0] - lat0) * m_per_deg
    return x, y


def _douglas_peucker(pts, tolerance_m):
    """Douglas-Peucker, splitting every open range of a recursion level in one numpy pass. Which
    point splits a range depends only on that range, so the order ranges are handled in doesn't
    change the result, and each one is measured exactly as on its own (see _douglas_peucker_one)."""
    if not np.all(np.isfinite(pts)):
        return _douglas_peucker_one(pts, tolerance_m)
    keep = np.zeros(len(pts), dtype=bool)
    keep[[0, -1]] = True
    m_per_deg = math.radians(MEAN_RADIUS_KM * METRES_PER["km"])
    i, j = np.array([0]), np.array([len(pts) - 1])
    while len(i):
        size = j - i + 1  # points in each range, ends included
        first = np.cumsum(size) - size  # where each range starts in the flat arrays
        rng = np.repeat(np.arange(len(i)), size)
        idx = np.arange(len(rng)) - np.repeat(first, size) + i[rng]
        # project around each range's start, scaled for its mean latitude
        lat0 = (pts[i, 0] + pts[j, 0]) / 2
        scale = np.array([math.cos(math.radians(v)) for v in lat0.tolist()])
        x = wrap_lon(pts[idx, 1] - pts[i, 1][rng]) * scale[rng] * m_per_deg
        y = (pts[idx, 0] - lat0[rng]) * m_per_deg
        x, y = x - x[first][rng], y - y[first][rng]
        last = first + size - 1
        dx, dy = x[last], y[last]
        seg2 = dx * dx + dy * dy
        dx, dy, seg2 = dx[rng], dy[rng], seg2[rng]
        with np.errstate(invalid="ignore", divide="ignore"):
            t = np.where(seg2 > 0, np.clip((x * dx + y * dy) / seg2, 0.0, 1.0), 0.0)
        dist = np.hypot(x - t * dx, y - t * dy)
        inner = np.ones(len(rng), dtype=bool)
        inner[first], inner[last] = False, False
        dist, inner_rng, inner_idx = dist[inner], rng[inner], idx[inner]
        starts = first - 2 * np.arange(len(i))  # each range's first inner point, ends dropped
        top = np.maximum.reduceat(dist, starts)
        hits = np.flatnonzero(dist == top[inner_rng])
        _, at = np.unique(inner_rng[hits], return_index=True)  # the first maximum of each range
        k = inner_idx[hits[at]]
        split = top > tolerance_m
        k = k[split]
        keep[k] = True
        i, j = np.r_[i[split], k], np.r_[k, j[split]]
        open_ = j - i >= 2
        i, j = i[open_], j[open_]
    return keep


def _douglas_peucker_one(pts, tolerance_m):
    keep = np.zeros(len(pts), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        # project around the segment's start, scaled for its mean latitude
        lat0 = (pts[i, 0] + pts[j, 0]) / 2
        x, y = _metres_xy(pts[i : j + 1], lat0, pts[i, 1])
        x, y = x - x[0], y - y[0]
        dx, dy = x[-1], y[-1]
        seg2 = dx * dx + dy * dy
        t = np.clip((x * dx + y * dy) / seg2, 0.0, 1.0) if seg2 > 0 else np.zeros_like(x)
        dist = np.hypot(x - t * dx, y - t * dy)[1:-1]
        k = int(np.argmax(dist))
        if dist[k] > tolerance_m:
            k += i + 1
            keep[k] = True
            stack += [(i, k), (k, j)]
    return keep


def _visvalingam(pts, tolerance_m):
    n = len(pts)
    threshold = tolerance_m * tolerance_m
    prev, nxt = list(range(-1, n - 1)), list(range(1, n + 1))
    keep = np.ones(n, dtype=bool)

    def area(k):
        # triangle with the current neighbours, projected around the middle vertex
        tri = pts[[prev[k], k, nxt[k]]]
        x, y = _metres_xy(tri, pts[k, 0], pts[k, 1])
        return abs((x[0] - x[1]) * (y[2] - y[1]) - (x[2] - x[1]) * (y[0] - y[1])) / 2

    current = [math.inf] * n
    heap = []
    for k in range(1, n - 1):
        current[k] = area(k)
        heap.append((current[k], k))
    heapq.heapify(heap)
    while heap:
        a, k = heapq.heappop(heap)
        if not keep[k] or a != current[k]:
            continue  # stale entry from before a neighbour was removed
        if a > threshold:
            break
        keep[k] = False
        p, q = prev[k], nxt[k]
        nxt[p], prev[q] = q, p
        for m in (p, q):
            if 0 < m < n - 1:
                current[m] = area(m)
                heapq.heappush(heap, (current[m], m))
    return keep
