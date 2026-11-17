"""Polygon clipping on the plane: intersection and difference of two simple rings (Greiner-Hormann).

G. Greiner and K. Hormann, "Efficient clipping of arbitrary polygons", ACM Transactions on Graphics
17(2), 1998: find every crossing of the two boundaries, label each crossing an entry into or an
exit from the other polygon, then walk the boundaries from crossing to crossing, switching polygon
at each. A ring is an (n, 2) array of (x, y) without its closing vertex, in either winding.

The method assumes no degenerate contact (a vertex on the other ring, overlapping collinear edges).
When one is found (DegenerateError) the clip ring is nudged by `NUDGE` (a few times, in
different directions) and
the clip retried; the result moves by no more than that, and slivers no wider than about ten
nudges (what a shared edge leaves) are dropped. Coordinates here are degrees, so the
nudge is about 0.1 mm, far below any boundary's accuracy.
"""

import numpy as np

NUDGE = 1e-9
_EPS = 1e-12  # crossing parameters this close to an edge's end are degenerate contacts
_TRIES = ((0, 0), (1, 0.37), (-0.61, 1), (0.83, -1), (-1, -0.29))
_BLOCK = 2_000_000  # edge pairs tested per numpy block


class DegenerateError(ValueError):
    """The rings touch at a vertex or along an edge, which the method can't label."""


def intersection(subject, clip):
    """The parts of `subject` inside `clip`: a list of rings."""
    return [p[0] for p in _clip(subject, clip, difference=False)]


def difference(subject, clip):
    """`subject` minus `clip`: a list of polygons, each [shell, *holes] (a hole only when the clip
    lies wholly inside the subject)."""
    return _clip(subject, clip, difference=True)


def inside(ring, x, y):
    """Even-odd test of points (arrays x, y) against one ring."""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    out = np.zeros(x.shape, dtype=bool)
    rx, ry = ring[:, 0], ring[:, 1]
    nx, ny = np.roll(rx, -1), np.roll(ry, -1)
    for k in range(len(ring)):  # loop over edges, vectorised over points
        crosses = (ry[k] > y) != (ny[k] > y)
        if crosses.any():
            at = rx[k] + (y - ry[k]) * (nx[k] - rx[k]) / np.where(ny[k] == ry[k], 1.0, ny[k] - ry[k])
            out ^= crosses & (x < at)
    return out


def _clip(subject, clip, difference):
    subject = _ring(subject)
    clip = _ring(clip)
    for dx, dy in _TRIES:
        try:
            polygons = _greiner_hormann(subject, clip + NUDGE * np.array([dx, dy]), difference)
        except DegenerateError:
            continue
        return [p for p in polygons if not _sliver(p[0])]
    raise DegenerateError("the rings still touch after nudging the clip ring")


def _sliver(ring):
    """A ring no wider than the nudge: what a shared edge leaves after nudging (area over
    perimeter is half the width of a long thin ring)."""
    x, y = ring[:, 0], ring[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y)))
    perimeter = float(np.hypot(*(np.roll(ring, -1, axis=0) - ring).T).sum())
    return area <= 10 * NUDGE * perimeter


def _ring(ring):
    ring = np.asarray(ring, dtype=np.float64)
    if len(ring) > 1 and np.array_equal(ring[0], ring[-1]):
        ring = ring[:-1]
    if len(ring) < 3:
        raise ValueError("a ring needs three or more vertices")
    return ring


def _crossings(a, b):
    """(i, j, t, u) for every crossing of edge i of ring a with edge j of ring b, at a[i] + t (a[i+1]
    - a[i]) = b[j] + u (b[j+1] - b[j]); DegenerateError on any contact that isn't a clean crossing."""
    a1, b1 = np.roll(a, -1, axis=0), np.roll(b, -1, axis=0)
    lo_a, hi_a = np.minimum(a, a1), np.maximum(a, a1)
    lo_b, hi_b = np.minimum(b, b1), np.maximum(b, b1)
    out = []
    step = max(1, _BLOCK // len(b))
    for s in range(0, len(a), step):
        sl = slice(s, s + step)
        near = (
            (lo_a[sl, None, 0] <= hi_b[None, :, 0])
            & (lo_b[None, :, 0] <= hi_a[sl, None, 0])
            & (lo_a[sl, None, 1] <= hi_b[None, :, 1])
            & (lo_b[None, :, 1] <= hi_a[sl, None, 1])
        )
        i, j = np.nonzero(near)
        if not len(i):
            continue
        i = i + s
        p, r = a[i], a1[i] - a[i]
        q, w = b[j], b1[j] - b[j]
        qp = q - p
        denom = r[:, 0] * w[:, 1] - r[:, 1] * w[:, 0]
        cross_qp_w = qp[:, 0] * w[:, 1] - qp[:, 1] * w[:, 0]
        cross_qp_r = qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]
        parallel = denom == 0
        if (parallel & (cross_qp_r == 0)).any():
            raise DegenerateError("collinear edges")
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(parallel, -1.0, cross_qp_w / np.where(parallel, 1.0, denom))
            u = np.where(parallel, -1.0, cross_qp_r / np.where(parallel, 1.0, denom))
        hit = (t >= -_EPS) & (t <= 1 + _EPS) & (u >= -_EPS) & (u <= 1 + _EPS)
        edge = hit & (
            (np.abs(t) <= _EPS) | (np.abs(t - 1) <= _EPS) | (np.abs(u) <= _EPS) | (np.abs(u - 1) <= _EPS)
        )
        if edge.any():
            raise DegenerateError("a vertex on the other ring")
        out.append(np.column_stack([i[hit], j[hit], t[hit], u[hit]]))
    return np.concatenate(out) if out else np.zeros((0, 4))


def _sequence(ring, edge, t, ids):
    """The ring's vertices with the crossings inserted in order along each edge: a list of
    (x, y, crossing id or -1), and each crossing's position in it."""
    order = np.lexsort((t, edge))
    seq, pos = [], np.zeros(len(ids), dtype=np.int64)
    k, n = 0, len(order)
    for v in range(len(ring)):
        seq.append((ring[v, 0], ring[v, 1], -1))
        while k < n and edge[order[k]] == v:
            c = int(ids[order[k]])
            pos[c] = len(seq)
            seq.append((None, None, c))
            k += 1
    return seq, pos


def _greiner_hormann(subject, clip, difference):
    found = _crossings(subject, clip)
    if not len(found):
        return _disjoint(subject, clip, difference)
    i, j, t, u = found[:, 0].astype(np.int64), found[:, 1].astype(np.int64), found[:, 2], found[:, 3]
    ids = np.arange(len(found))
    points = subject[i] + t[:, None] * (np.roll(subject, -1, axis=0)[i] - subject[i])
    seq_s, pos_s = _sequence(subject, i, t, ids)
    seq_c, pos_c = _sequence(clip, j, u, ids)
    entry_s = _entries(seq_s, len(ids), bool(inside(clip, subject[0, 0], subject[0, 1])))
    entry_c = _entries(seq_c, len(ids), bool(inside(subject, clip[0, 0], clip[0, 1])))
    if difference:  # walk the subject outside the clip, the clip inside the subject
        entry_s = ~entry_s
    walks = ((seq_s, pos_s, entry_s), (seq_c, pos_c, entry_c))
    visited = np.zeros(len(ids), dtype=bool)
    out = []
    for start in range(len(ids)):
        if visited[start]:
            continue
        ring, c, on = [], start, 0
        while True:
            visited[c] = True
            ring.append(points[c])
            seq, pos, entry = walks[on]
            step = 1 if entry[c] else -1
            k = (pos[c] + step) % len(seq)
            while seq[k][2] < 0:
                ring.append((seq[k][0], seq[k][1]))
                k = (k + step) % len(seq)
            c, on = seq[k][2], 1 - on
            if c == start:
                break
        out.append([np.asarray(ring, dtype=np.float64)])
    return out


def _entries(seq, n, start_inside):
    """Per crossing, whether walking forward along the ring enters the other polygon there."""
    entry = np.zeros(n, dtype=bool)
    now = start_inside
    for _, _, c in seq:
        if c >= 0:
            entry[c] = not now
            now = not now
    return entry


def _disjoint(subject, clip, difference):
    """Boundaries that never cross: one ring holds the other, or they are apart."""
    s_in_c = bool(inside(clip, subject[0, 0], subject[0, 1]))
    c_in_s = bool(inside(subject, clip[0, 0], clip[0, 1]))
    if difference:
        if s_in_c:
            return []
        return [[subject, clip]] if c_in_s else [[subject]]
    if s_in_c:
        return [[subject]]
    return [[clip]] if c_in_s else []
