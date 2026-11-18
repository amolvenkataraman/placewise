"""A point inside every polygon feature, and the feature's radius around it, for the name index.

The point is the feature's label point when one is given and it is inside; otherwise the middle of
the widest stretch of a few horizontal lines across the feature's largest polygon that lies
inside it (even-odd over all the feature's rings, as the readers test). Every point is checked with
the readers' own test after rounding to the 1e-7 storage grid, so it is inside as the pack sees it.
"""

import numpy as np

from placewise.geo import haversine

from . import _geometry as gm

# where the lines cross the largest polygon's latitude span, most central first
_FRACTIONS = np.array([0.5, 0.37, 0.63, 0.23, 0.77, 0.1, 0.9])
_EDGE_BUDGET = 2_000_000  # edges x lines examined at once


def points(geom, hint=None):
    """((n, 2) int32 e7 lat/lon, (n,) float32 radius_km) for a prepared polygon layer's geometry
    (the writer's geom dict); `hint` is an optional (lat, lon) pair of arrays, NaN where none."""
    lat, lon = gm.from_e7(geom["lat.npy"]), gm.from_e7(geom["lon.npy"])
    ring, part, feature = geom["ring.npy"], geom["part.npy"], geom["feature.npy"]
    n = len(feature) - 1
    nxt = gm.ring_next(ring, len(lat))
    edges = (lat, lon, lat[nxt], lon[nxt])
    offsets = ring[part[feature]]  # each feature's vertices (and edges) are one slice
    out = np.full((n, 2), np.nan)
    if hint is not None:
        h_lat, h_lon = (np.asarray(h, dtype=np.float64).reshape(n) for h in hint)
        ok = np.flatnonzero(np.isfinite(h_lat) & np.isfinite(h_lon))
        h_lat, h_lon = gm.from_e7(gm.to_e7(h_lat[ok])), gm.from_e7(gm.to_e7(h_lon[ok]))
        inside = gm.even_odd_pairs(h_lat, h_lon, ok, offsets, *edges)
        out[ok[inside]] = np.column_stack([h_lat[inside], h_lon[inside]])
    todo = np.flatnonzero(np.isnan(out[:, 0]))
    if len(todo):
        out[todo] = _scanline_points(todo, ring, part, feature, offsets, edges)
    radius = np.zeros(n, dtype=np.float32)
    if n:
        owner = np.repeat(np.arange(n), np.diff(offsets))
        far = haversine(lat, lon, out[owner, 0], out[owner, 1])
        radius = np.maximum.reduceat(far, offsets[:-1]).astype(np.float32)
    return gm.to_e7(out), radius


def _scanline_points(todo, ring, part, feature, offsets, edges):
    """Inside points for the features `todo`, chunked so memory stays bounded."""
    lo, hi = _largest_part_span(ring, part, feature, edges)
    out = np.empty((len(todo), 2))
    cost = np.cumsum((offsets[todo + 1] - offsets[todo]) * len(_FRACTIONS))
    start = 0
    while start < len(todo):
        stop = max(start + 1, int(np.searchsorted(cost, (cost[start - 1] if start else 0) + _EDGE_BUDGET)))
        chunk = todo[start:stop]
        out[start:stop] = _chunk_points(chunk, lo[chunk], hi[chunk], offsets, edges)
        start = stop
    return out


def _largest_part_span(ring, part, feature, edges):
    """Per feature, the latitude span of the outer ring of its largest polygon (by planar area)."""
    ya, xa, yb, xb = edges
    starts = ring[:-1]
    area = np.abs(np.add.reduceat(xa * yb - xb * ya, starts))[part[:-1]]
    lo, hi = np.minimum.reduceat(ya, starts)[part[:-1]], np.maximum.reduceat(ya, starts)[part[:-1]]
    owner = np.repeat(np.arange(len(feature) - 1), np.diff(feature))
    order = np.lexsort((-area, owner))
    best = order[np.r_[True, owner[order][1:] != owner[order][:-1]]]
    return lo[best], hi[best]


def _chunk_points(chunk, lo, hi, offsets, edges):
    ya, xa, yb, xb = edges
    owner, edge = gm._expand(offsets[chunk], offsets[chunk + 1])
    k = len(_FRACTIONS)
    lines = lo[:, None] + _FRACTIONS[None, :] * (hi - lo)[:, None]  # (chunk, k)
    # every edge against each of its feature's lines
    e = np.repeat(edge, k)
    line = np.tile(np.arange(k), len(edge))
    f = np.repeat(owner, k)
    y = lines[f, line]
    e_ya, e_yb = ya[e], yb[e]
    cross = (e_ya <= y) != (e_yb <= y)
    e, f, line, y = e[cross], f[cross], line[cross], y[cross]
    x = xa[e] + (y - ya[e]) * (xb[e] - xa[e]) / (yb[e] - ya[e])
    group = f * k + line
    order = np.lexsort((x, group))
    group, x = group[order], x[order]
    starts = np.flatnonzero(np.r_[True, group[1:] != group[:-1]])
    pos = np.arange(len(group)) - np.repeat(starts, np.diff(np.r_[starts, len(group)]))
    # stretches between the 1st and 2nd crossing, the 3rd and 4th ...: inside by even-odd
    a = np.flatnonzero((pos % 2 == 0) & (np.r_[group[1:], -1] == group))
    width = x[a + 1] - x[a]
    cand_f = group[a] // k
    cand_lat = lines[cand_f, group[a] % k]
    cand_lon = (x[a] + x[a + 1]) / 2
    cand_lat, cand_lon = gm.from_e7(gm.to_e7(cand_lat)), gm.from_e7(gm.to_e7(cand_lon))
    ok = gm.even_odd_pairs(cand_lat, cand_lon, chunk[cand_f], offsets, ya, xa, yb, xb)
    out = np.column_stack([ya[offsets[chunk]], xa[offsets[chunk]]])  # a vertex, if all else fails
    good = np.flatnonzero(ok)
    pick = good[np.lexsort((-width[good], cand_f[good]))]
    first = np.r_[True, cand_f[pick][1:] != cand_f[pick][:-1]] if len(pick) else np.zeros(0, bool)
    pick = pick[first]
    out[cand_f[pick]] = np.column_stack([cand_lat[pick], cand_lon[pick]])
    return out
