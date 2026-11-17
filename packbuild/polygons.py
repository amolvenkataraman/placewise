"""Projected polygon rings into placewise Features: simplify in metres, unproject, group holes.

Rings come as (n, 2) arrays of projected (x, y) metres, in the shapefile / Esri JSON convention:
outer rings clockwise, holes counter-clockwise. Simplifying before unprojecting means the tolerance
is a distance on the ground (Lambert conformal conic keeps scale within a few percent across
southern Canada), not a fraction of a degree that shrinks with latitude.

Each feature is simplified on its own (Douglas-Peucker), so the shared border of two neighbours
can differ by up to the tolerance: a sliver of that width may belong to both or to neither.

Douglas-Peucker and the unprojection run on many rings at once (`simplify_rings`, `to_features`),
with each ring's own arithmetic and stopping rules, so the result is the one ring-by-ring calls
give, only without a Python loop per vertex split.
"""

import itertools

import numpy as np

from placewise.model import Feature, Outline

# vertices simplified and unprojected at once by to_features: bounds the working memory
_BATCH_VERTICES = 2_000_000


def signed_area(ring):
    """Shoelace area of an (n, 2) ring; negative when it runs clockwise (x east, y north)."""
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, _shift(y)) - np.dot(_shift(x), y))


def _shift(a):
    """np.roll(a, -1) for a 1-d array, without its overhead."""
    return np.concatenate((a[1:], a[:1]))


def simplify_ring(ring, tolerance):
    """The ring without its closing vertex, simplified with Douglas-Peucker to `tolerance` (same
    units as the coordinates); None when it collapses below three vertices. tolerance <= 0 only
    drops the closing vertex."""
    return simplify_rings([ring], tolerance)[0]


def simplify_rings(rings, tolerance):
    """`simplify_ring` of each ring, all rings at once."""
    out = [None] * len(rings)
    pts_list = []
    for k, ring in enumerate(rings):
        pts = np.asarray(ring, dtype=np.float64)
        if len(pts) > 1 and np.array_equal(pts[0], pts[-1]):
            pts = pts[:-1]
        if len(pts) >= 3:
            if tolerance <= 0:
                out[k] = pts
            else:
                pts_list.append((k, pts))
    if not pts_list:
        return out
    which = np.array([k for k, _ in pts_list], dtype=np.int64)
    pts = np.vstack([p for _, p in pts_list])
    sizes = np.array([len(p) for _, p in pts_list], dtype=np.int64)
    starts = np.cumsum(sizes) - sizes
    ring_of = np.repeat(np.arange(len(sizes)), sizes)
    # split each closed ring at its first vertex and the vertex farthest from it
    from_first = np.hypot(pts[:, 0] - pts[starts, 0][ring_of], pts[:, 1] - pts[starts, 1][ring_of])
    far = _first_argmax(from_first, starts) - starts
    ok = far > 0
    which, starts, sizes, far = which[ok], starts[ok], sizes[ok], far[ok]
    # the two halves of ring r as polylines: its vertices 0..far, then far..n-1 and 0 again
    first_len, second_len = far + 1, sizes - far + 1
    line_len = np.column_stack([first_len, second_len]).ravel()
    line_start = np.cumsum(line_len) - line_len
    owner, pos = _expand(np.zeros(len(line_len), dtype=np.int64), line_len)
    ring_k = owner // 2
    second = (owner % 2).astype(bool)
    local = np.where(second, (far[ring_k] + pos) % sizes[ring_k], pos)
    line = pts[starts[ring_k] + local]
    keep = _keep_many(line, line_start, line_start + line_len - 1, tolerance)
    keep[line_start + line_len - 1] = False  # each half's last vertex starts the other half
    counts = np.bincount(ring_k[keep], minlength=len(which))
    kept = np.split(line[keep], np.cumsum(counts)[:-1])
    for k, ring_pts, n in zip(which.tolist(), kept, counts.tolist(), strict=True):
        if n >= 3:
            out[k] = ring_pts
    return out


def _keep_many(line, starts, ends, tolerance):
    """Douglas-Peucker on every polyline line[starts[k] : ends[k] + 1] at once: a mask of the
    vertices to keep (always both ends). Each level of the recursion splits every open segment at
    its farthest vertex (the first, on a tie) while that is farther than `tolerance`."""
    x, y = np.ascontiguousarray(line[:, 0]), np.ascontiguousarray(line[:, 1])
    keep = np.zeros(len(line), dtype=bool)
    keep[starts] = keep[ends] = True
    i, j = np.asarray(starts, dtype=np.int64), np.asarray(ends, dtype=np.int64)
    while True:
        wide = j - i >= 2
        i, j = i[wide], j[wide]
        if not len(i):
            return keep
        seg, idx = _expand(i + 1, j)
        ax, ay = x[i], y[i]
        dx, dy = x[j] - ax, y[j] - ay
        length = np.hypot(dx, dy)
        px, py = x[idx] - ax[seg], y[idx] - ay[seg]
        dist = np.empty(len(idx))
        flat = length[seg] == 0
        dist[flat] = np.hypot(px[flat], py[flat])
        s = ~flat
        dist[s] = np.abs(dx[seg][s] * py[s] - dy[seg][s] * px[s]) / length[seg][s]
        seg_start = np.cumsum(j - i - 1) - (j - i - 1)
        best = _first_argmax(dist, seg_start)
        split = dist[best] > tolerance
        k = idx[best][split]
        keep[k] = True
        i, j = np.concatenate([i[split], k]), np.concatenate([k, j[split]])


def _first_argmax(values, starts):
    """Per segment values[starts[s]:starts[s + 1]] (non-empty, the last running to the end): the
    position of its largest value, the first one on a tie, as np.argmax."""
    seg_max = np.maximum.reduceat(values, starts)
    seg = np.repeat(np.arange(len(starts)), np.diff(np.append(starts, len(values))))
    hit = np.flatnonzero(values == seg_max[seg])
    _, first = np.unique(seg[hit], return_index=True)
    return hit[first]


def _expand(start, stop):
    """(owner, i) for every i in each [start, stop) range."""
    counts = np.maximum(stop - start, 0)
    owner = np.repeat(np.arange(len(start)), counts)
    first = np.cumsum(counts) - counts
    return owner, np.arange(int(counts.sum()), dtype=np.int64) - np.repeat(first - start, counts)


def to_feature(rings, tolerance, projection, fid):
    """A Feature (with id `fid`) from one record's projected rings. Rings smaller than the tolerance
    are dropped, with their holes; a feature that would vanish entirely keeps its largest ring as
    drawn, so every record still has a shape."""
    return to_features([(rings, fid)], tolerance, projection)[0]


def to_features(records, tolerance, projection):
    """`to_feature` of each (rings, fid) record, simplifying and unprojecting many at once."""
    out, batch, size = [], [], 0
    for rings, fid in records:
        plan = _plan(rings, fid)
        batch.append(plan)
        size += sum(len(r) for r in plan[0])
        if size >= _BATCH_VERTICES:
            out += _build(batch, tolerance, projection)
            batch, size = [], 0
    return out + _build(batch, tolerance, projection)


def _plan(rings, fid):
    """(open rings, outer ring indexes, {outer: its holes}, signed areas, fid) for one record."""
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
    return rings, outer, holes, areas, fid


def _build(plans, tolerance, projection):
    # every shell and hole of every plan, simplified at once, then unprojected at once
    todo = [rings[i] for rings, outer, holes, _, _ in plans for o in outer for i in (o, *holes[o])]
    simple = iter(simplify_rings(todo, tolerance))
    groups = []  # per plan: list of outlines, each a list of rings (projected)
    for rings, outer, holes, areas, _ in plans:
        outlines = []
        for o in outer:
            shell = next(simple)
            kept = [h for h in (next(simple) for _ in holes[o]) if h is not None]
            if shell is not None:
                outlines.append([shell, *kept])
        if not outlines:
            largest = max(outer, key=lambda i: abs(areas[i]))
            outlines.append([rings[largest]])
        groups.append(outlines)
    flat = [r for outlines in groups for o in outlines for r in o]
    unprojected = iter(_latlon_many(flat, projection))
    return [
        Feature(tuple(Outline(tuple(next(unprojected) for _ in o)) for o in outlines), {}, plan[4])
        for outlines, plan in zip(groups, plans, strict=True)
    ]


def _inside(ring, p):
    """Even-odd test of one point against one ring."""
    x, y = ring[:, 0], ring[:, 1]
    xn, yn = _shift(x), _shift(y)
    crosses = (y > p[1]) != (yn > p[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        at = x + (p[1] - y) * (xn - x) / (yn - y)
    return bool(np.count_nonzero(crosses & (p[0] < at)) % 2)


def _latlon(ring, projection):
    return _latlon_many([ring], projection)[0]


def _latlon_many(rings, projection):
    """Each ring unprojected to a tuple of (lat, lon) pairs, as `projection.inverse` gives it."""
    if not rings:
        return []
    sizes = np.array([len(r) for r in rings], dtype=np.int64)
    offsets = np.concatenate([[0], np.cumsum(sizes)])
    pts = np.vstack(rings)
    inverse_rings = getattr(projection, "inverse_rings", None)
    if inverse_rings is None:
        lon, lat = projection.inverse(pts[:, 0], pts[:, 1])
    else:
        lon, lat = inverse_rings(pts[:, 0], pts[:, 1], offsets)
    lat, lon = np.asarray(lat).tolist(), np.asarray(lon).tolist()
    return [tuple(zip(lat[a:b], lon[a:b], strict=True)) for a, b in itertools.pairwise(offsets)]
