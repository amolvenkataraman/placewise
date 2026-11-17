"""Split polygons along another set of polygons, without a geometry library: the parts of each
subject inside and outside a clip region (planar, in longitude/latitude, even-odd over all rings).

The India Post PIN areas follow India's official boundary, so some reach into ground other
countries administer (Gilgit-Baltistan, Aksai Chin ...). `split` cuts them along the world pack's
de facto country polygons so each piece can carry `india_view_only`.

How: every subject edge is cut where it crosses a clip edge and every clip edge where it crosses
the subject; each intersection point is computed once and shared, so the pieces meet exactly. A
subject piece whose midpoint is inside the clip region bounds the inside part, otherwise the
outside part; a clip piece whose midpoint is inside the subject bounds both (reversed for the
outside part). Stitching those edges into cycles gives rings with the same even-odd answer as the
true intersection and difference: a point's crossing count depends only on the set of edges, not
on how they are joined. Edges lying exactly along each other (independent sources: practically
never) would be counted on whichever side their midpoint test falls.
"""

import numpy as np

from ..regions_layer import _cycles, dissolve


def inside(rings, x, y):
    """Even-odd test of points (x, y arrays) against rings ((n, 2) arrays): a bool array."""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    odd = np.zeros(len(x), dtype=bool)
    for ring in rings:
        ax, ay = ring[:, 0], ring[:, 1]
        bx, by = np.roll(ax, -1), np.roll(ay, -1)
        for s in range(0, len(x), 2048):
            px, py = x[s : s + 2048, None], y[s : s + 2048, None]
            crosses = (ay > py) != (by > py)
            with np.errstate(divide="ignore", invalid="ignore"):
                at = ax + (py - ay) * (bx - ax) / (by - ay)
            odd[s : s + 2048] ^= (np.count_nonzero(crosses & (px < at), axis=1) % 2).astype(bool)
    return odd


def _edges(rings):
    """(start (m, 2), end (m, 2)) of every ring edge."""
    if not rings:
        empty = np.zeros((0, 2))
        return empty, empty
    a = np.vstack(rings)
    b = np.vstack([np.roll(r, -1, axis=0) for r in rings])
    return a, b


def _crossings(sa, sb, ca, cb, cell=0.02):
    """(subject edge, clip edge, t along subject, u along clip, point) for every proper crossing.
    Candidate pairs come from a grid of `cell` degrees: edges whose boxes share a cell."""
    if not len(sa) or not len(ca):
        none = np.zeros(0, dtype=np.int64)
        return none, none, np.zeros(0), np.zeros(0), np.zeros((0, 2))
    i, j = _pairs(np.minimum(sa, sb), np.maximum(sa, sb), np.minimum(ca, cb), np.maximum(ca, cb), cell)
    p, r = sa[i], sb[i] - sa[i]
    q, w = ca[j], cb[j] - ca[j]
    denom = r[:, 0] * w[:, 1] - r[:, 1] * w[:, 0]
    qp = q - p
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[:, 0] * w[:, 1] - qp[:, 1] * w[:, 0]) / denom
        u = (qp[:, 0] * r[:, 1] - qp[:, 1] * r[:, 0]) / denom
    ok = (denom != 0) & (t > 0) & (t < 1) & (u > 0) & (u < 1)
    i, j, t, u = i[ok], j[ok], t[ok], u[ok]
    return i, j, t, u, p[ok] + t[:, None] * r[ok]


def _cells(lo, hi, cell, origin):
    """(edge index, cell key) for every grid cell each box touches."""
    c0 = np.floor((lo - origin) / cell).astype(np.int64)
    c1 = np.floor((hi - origin) / cell).astype(np.int64)
    nx, ny = c1[:, 0] - c0[:, 0] + 1, c1[:, 1] - c0[:, 1] + 1
    count = nx * ny
    edge = np.repeat(np.arange(len(lo)), count)
    k = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    gx = c0[edge, 0] + k % nx[edge]
    gy = c0[edge, 1] + k // nx[edge]
    return edge, gx * 1_000_003 + gy


def _pairs(amin, amax, bmin, bmax, cell):
    """Unique (a, b) index pairs whose boxes overlap."""
    origin = np.minimum(amin.min(axis=0), bmin.min(axis=0))
    ea, ka = _cells(amin, amax, cell, origin)
    eb, kb = _cells(bmin, bmax, cell, origin)
    order = np.argsort(kb, kind="stable")
    eb, kb = eb[order], kb[order]
    start, stop = np.searchsorted(kb, ka, "left"), np.searchsorted(kb, ka, "right")
    n = stop - start
    i = np.repeat(ea, n)
    pos = np.repeat(start - (np.cumsum(n) - n), n) + np.arange(n.sum())
    j = eb[pos]
    if len(i):
        key = np.unique(i.astype(np.int64) * len(bmin) + j)
        i, j = key // len(bmin), key % len(bmin)
    overlap = np.all((amin[i] <= bmax[j]) & (bmin[j] <= amax[i]), axis=1)
    return i[overlap], j[overlap]


def _pieces(a, b, edge, along, points):
    """Edges a->b cut at `points` (on edge `edge`, at fraction `along`): (starts, ends)."""
    if not len(edge):
        return a, b
    order = np.lexsort((along, edge))
    edge, points = edge[order], points[order]
    starts, ends = [], []
    cut = np.zeros(len(a), dtype=bool)
    cut[edge] = True
    starts.append(a[~cut])
    ends.append(b[~cut])
    bounds = np.flatnonzero(np.r_[True, edge[1:] != edge[:-1], True])
    for k in range(len(bounds) - 1):
        e = edge[bounds[k]]
        mids = points[bounds[k] : bounds[k + 1]]
        chain = np.vstack([a[e], mids, b[e]])
        starts.append(chain[:-1])
        ends.append(chain[1:])
    return np.vstack(starts), np.vstack(ends)


def split(subject, clip, in_clip=None):
    """(inside rings, outside rings): the subject's rings (shells clockwise, holes
    counter-clockwise, (n, 2) x/y arrays) cut along the clip's rings (the same convention). Either
    list may be empty. `in_clip(x, y) -> bool array` answers "is this point in the clip region?"
    (default: even-odd over `clip`); pass a faster index for a big clip region, and then only the
    clip rings near the subject: clip edges outside the subject's box can't bound either part."""
    if not subject:
        return [], []
    ca, cb = _edges(clip)
    if in_clip is None:
        rings = list(clip)

        def in_clip(x, y):
            return inside(rings, x, y)

    return split_edges(subject, ca, cb, in_clip)


def split_edges(subject, ca, cb, in_clip):
    """split with the clip region given as edges (ca -> cb, (m, 2) arrays): only those near the
    subject matter, and `in_clip(x, y)` answers membership for the whole region."""
    sa, sb = _edges(subject)
    if not len(sa):
        return [], []
    i, j, t, u, points = _crossings(sa, sb, ca, cb)
    s0, s1 = _pieces(sa, sb, i, t, points)
    c0, c1 = _pieces(ca, cb, j, u, points)
    smid, cmid = (s0 + s1) / 2, (c0 + c1) / 2
    s_in = np.asarray(in_clip(smid[:, 0], smid[:, 1]), dtype=bool)
    c_in = inside(subject, cmid[:, 0], cmid[:, 1])
    inner = _rings(np.vstack([s0[s_in], c0[c_in]]), np.vstack([s1[s_in], c1[c_in]]))
    outer = _rings(np.vstack([s0[~s_in], c1[c_in]]), np.vstack([s1[~s_in], c0[c_in]]))
    return inner, outer


def _rings(starts, ends):
    """Directed edges stitched into rings, opposite duplicates cancelled (regions_layer.dissolve)."""
    if not len(starts):
        return []
    vertices, index = np.unique(np.vstack([starts, ends]), axis=0, return_inverse=True)
    index = index.ravel()
    src, dst = index[: len(starts)], index[len(starts) :]
    keep = src != dst
    cycles = _cycles(src[keep].tolist(), dst[keep].tolist())
    return dissolve([vertices[c] for c in cycles])
