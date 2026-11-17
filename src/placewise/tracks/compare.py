"""Comparing tracks: Hausdorff and discrete Fréchet distances, how much of each lies within a
corridor around the other ("same route?") and where a track left a reference ("off route where?").

A track is compared as its polyline: the great-circle steps between consecutive fixes, leaving out
the jump across a segment break (nothing was recorded there); a one-fix segment counts as that
point. Distances are on the sphere, from fixes to the nearest point of the other polyline (point to
segment, not point to point), so differently sampled recordings of one path come out close.

Big comparisons stay fast by ruling pairs out before measuring them exactly, with the triangle
inequality twice: consecutive fixes and steps are grouped into blocks of _BLOCK inside spherical
caps, and only step blocks that could hold a fix block's nearest step survive; then, fix by fix,
only steps whose nearer end, less half the step, is no further than the nearest step end so far.
That leaves a few exact point-to-arc distances per fix for tracks that run near each other.
"""

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.tracks import (
    CORRIDOR_M,
    DEVIATION_CORRIDOR_M,
    FRECHET_SIMPLIFY_M,
    SAME_ROUTE_MIN_OVERLAP,
)
from placewise.geo.bearing import along
from placewise.geo.lines import _angle, _nearest_on_arcs, simplify
from placewise.model._base import Model

from ._ops import M_PER_KM, in_segment_steps, step_km, unit_vectors

_BLOCK = 8  # fixes or steps per cap: small enough for tight caps, big enough to vectorise
_PAIRS = 1 << 20  # fix-step pairs screened at once, which bounds temporary memory
_CAP_PAIRS = 1 << 20  # cap-to-cap angles computed at once
# radians of allowance on the bounds: arccos of a dot product is only good to ~1.5e-8 near 0
_SLACK = 1e-7


class Overlap(NamedTuple):
    a_in_b: float  # fraction of a's length within the corridor around b
    b_in_a: float


@dataclass(frozen=True, slots=True)
class Deviation(Model):
    """A stretch of track beyond the corridor around a reference route."""

    start: float  # when the track left the corridor (interpolated between fixes)
    end: float  # when it came back
    first_index: int  # first and last fix outside
    last_index: int
    max_distance_km: float
    lat: float  # the fix farthest from the reference
    lon: float


def hausdorff_km(a, b):
    """Symmetric Hausdorff distance (km): the farthest any fix of either track is from the other
    track's polyline. Measured from fixes, so a long step bowing away between two fixes counts
    only at its ends; resample(every_m=...) first to measure along it too."""
    to_b, to_a = _to_line(_fixes(a), _Line(b)), _to_line(_fixes(b), _Line(a))
    return float(max(to_b.max(), to_a.max()) * MEAN_RADIUS_KM)


def frechet_km(a, b, simplify_m=FRECHET_SIMPLIFY_M):
    """Discrete Fréchet distance (km) between the fixes of a and b: the shortest leash that lets
    two walkers, each stepping forwards from fix to fix, cover both tracks. Unlike Hausdorff it
    respects direction and order, so a route and its reverse are far apart. Always at least the
    Hausdorff distance.

    simplify_m simplifies both tracks first (Douglas-Peucker, tolerance in metres) for speed; the
    walkers then step between the remaining vertices, which on long straight stretches can add up
    to half their spacing. The DP keeps only two anti-diagonals of the n x m table, O(n + m)
    memory, and each anti-diagonal is one vectorised step."""
    pa, pb = _fixes(a, simplify_m), _fixes(b, simplify_m)
    return float(_discrete_frechet(pa, pb) * MEAN_RADIUS_KM)


def overlap(a, b, corridor_m=CORRIDOR_M):
    """Overlap(a_in_b, b_in_a): the fraction of a's length within corridor_m metres of b's polyline,
    and of b's within a's. Both near 1 means the same route; a_in_b near 1 alone means a runs
    along part of b. Steps are measured at points no further apart than corridor_m, with the
    corridor edge interpolated between them. A track of no length scores the share of its fixes
    inside."""
    return Overlap(_inside_share(a, _Line(b), corridor_m), _inside_share(b, _Line(a), corridor_m))


def same_route(a, b, corridor_m=CORRIDOR_M, min_overlap=SAME_ROUTE_MIN_OVERLAP):
    """Whether at least min_overlap of each track lies within corridor_m metres of the other."""
    return min(overlap(a, b, corridor_m)) >= min_overlap


def deviations(track, reference, corridor_m=DEVIATION_CORRIDOR_M):
    """Stretches of `track` further than corridor_m metres from the reference polyline, as a list of
    Deviation in track order. Each runs over consecutive fixes outside the corridor; where it
    leaves and rejoins is interpolated between the fixes either side, linearly in distance and
    time, within a segment (at a segment break the first or last fix outside is used). A stretch
    outside on both sides of a recording gap stays one deviation."""
    n = len(track)
    if n == 0:
        return []
    d_km = _to_line(unit_vectors(track.lat, track.lon), _Line(reference)) * MEAN_RADIUS_KM
    d = d_km * M_PER_KM
    outside = d > corridor_m
    if not outside.any():
        return []
    edges = np.diff(np.r_[0, outside.astype(np.int8), 0])
    firsts, lasts = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1) - 1
    within, t = in_segment_steps(track), track.time
    found = []
    for f, last in zip(firsts.tolist(), lasts.tolist(), strict=True):
        start, end = t[f], t[last]
        if f > 0 and within[f - 1]:
            start = t[f - 1] + (corridor_m - d[f - 1]) / (d[f] - d[f - 1]) * (t[f] - t[f - 1])
        if last < n - 1 and within[last]:
            end = t[last] + (d[last] - corridor_m) / (d[last] - d[last + 1]) * (t[last + 1] - t[last])
        k = f + int(np.argmax(d[f : last + 1]))
        found.append(
            Deviation(
                float(start), float(end), f, last, float(d_km[k]), float(track.lat[k]), float(track.lon[k])
            )
        )
    return found


# -- polylines and their bounding caps ---------------------------------------------------------


class _Line:
    """A track's polyline as great-circle steps (unit vectors a -> b), with a cap around each
    block of _BLOCK consecutive steps."""

    __slots__ = ("a", "b", "centre", "half", "radius")

    def __init__(self, track):
        n = len(track)
        if n == 0:
            raise ValueError("an empty track has no line to compare against")
        u = unit_vectors(track.lat, track.lon)
        steps = np.flatnonzero(in_segment_steps(track))
        starts = np.asarray(track.segments)
        lone = starts[np.diff(np.r_[starts, n]) == 1]  # one-fix segments: a step from it to itself
        order = np.argsort(np.r_[steps, lone], kind="stable")
        self.a = u[np.r_[steps, lone][order]]
        self.b = u[np.r_[steps + 1, lone][order]]
        self.half = _angle(self.a, self.b) / 2
        self.centre, self.radius = _caps(self.a, self.b)


def _fixes(track, simplify_m=None):
    if len(track) == 0:
        raise ValueError("an empty track can't be compared")
    lat, lon = track.lat, track.lon
    if simplify_m:
        keep = simplify(np.column_stack([lat, lon]), simplify_m)
        lat, lon = lat[keep], lon[keep]
    return unit_vectors(lat, lon)


def _caps(first, second):
    """(centres, radii) of caps holding rows first[i] and second[i] of each block of _BLOCK rows.
    Radii beyond 90° become pi (no bound): only caps under a hemisphere are convex, i.e. hold
    the arcs between their points."""
    n = len(first)
    starts = np.arange(0, n, _BLOCK)
    sums = np.add.reduceat(first, starts, axis=0) + np.add.reduceat(second, starts, axis=0)
    norm = np.linalg.norm(sums, axis=1)
    centre = sums / np.where(norm > 0, norm, 1.0)[:, None]
    of = centre[np.arange(n) // _BLOCK]
    radius = np.maximum.reduceat(np.maximum(_angle(first, of), _angle(second, of)), starts)
    return centre, np.where((norm > 0) & (radius < np.pi / 2), radius + _SLACK, np.pi)


def _cap_angles(centres, line):
    """Angles (k, blocks) between cap centres and the line's cap centres."""
    return np.arccos(np.clip(centres @ line.centre.T, -1.0, 1.0))


def _to_line(points, line):
    """Angular distance (radians) from every point (unit vectors, consecutive along a track) to
    the line."""
    out = np.full(len(points), np.inf)
    centre, radius = _caps(points, points)
    for blocks in _block_pairs(centre, radius, line):
        _measure(points, line, blocks, out)
    return out


def _block_pairs(centre, radius, line):
    """Chunks of (fix block, step block) index pairs that could hold each fix's nearest step.

    For a fix in a cap of radius r_p and any point x on a step in a step cap at angle D, the
    triangle inequality gives D - r_p - r_s <= |fix x|, and the step cap's endpoints lie within
    D + r_p + r_s. So only step blocks whose lower bound is within the fix block's best upper
    bound can matter."""
    rows = max(1, _CAP_PAIRS // len(line.centre))
    per = max(1, _PAIRS // (_BLOCK * _BLOCK))
    for r in range(0, len(centre), rows):
        d = _cap_angles(centre[r : r + rows], line)
        reach = radius[r : r + rows, None] + line.radius[None, :]
        upper = np.min(d + reach, axis=1) + _SLACK
        fix_block, step_block = np.nonzero(d - reach <= upper[:, None])
        for c in range(0, len(fix_block), per):
            yield fix_block[c : c + per] + r, step_block[c : c + per]


def _measure(points, line, blocks, out):
    """Lower `out` to the distance from each fix to the nearest step among the block pairs."""
    fix_block, step_block = blocks
    offsets = np.arange(_BLOCK)
    fix = (fix_block[:, None, None] * _BLOCK + offsets[None, :, None]).repeat(_BLOCK, axis=2).ravel()
    step = (step_block[:, None, None] * _BLOCK + offsets[None, None, :]).repeat(_BLOCK, axis=1).ravel()
    valid = (fix < len(points)) & (step < len(line.a))
    fix, step = fix[valid], step[valid]
    p = points[fix]
    # the nearer end of each step is a real point of the line: its distance bounds the fix's
    # distance from above; and no point of a step is more than half its length from an end
    end = np.minimum(_chord_angle(p, line.a[step]), _chord_angle(p, line.b[step]))
    upper = np.full(len(points), np.inf)
    np.minimum.at(upper, fix, end)
    keep = end - line.half[step] <= upper[fix] + _SLACK
    fix, step = fix[keep], step[keep]
    _, angle, _ = _nearest_on_arcs(points[fix], line.a[step], line.b[step])
    np.minimum.at(out, fix, angle)


def _chord_angle(u, v):
    """Angle between unit vectors from their chord, accurate down to millimetres."""
    return 2 * np.arcsin(np.minimum(1.0, np.linalg.norm(u - v, axis=-1) / 2))


# -- overlap ------------------------------------------------------------------------------------


def _inside_share(track, line, corridor_m):
    lat, lon, piece_m, recorded = _densify(track, corridor_m)
    d = _to_line(unit_vectors(lat, lon), line) * MEAN_RADIUS_KM * M_PER_KM
    piece_m = piece_m[recorded]
    total = float(np.sum(piece_m))
    if total == 0:
        return float(np.mean(d <= corridor_m))
    d0, d1 = d[:-1][recorded], d[1:][recorded]
    in0, in1 = d0 <= corridor_m, d1 <= corridor_m
    with np.errstate(invalid="ignore", divide="ignore"):
        edge = (corridor_m - d0) / (d1 - d0)  # where the distance crosses the corridor edge
    share = np.where(in0 & in1, 1.0, np.where(in0 != in1, np.where(in0, edge, 1.0 - edge), 0.0))
    return float(np.sum(piece_m * share) / total)


def _densify(track, step_m):
    """Points along the track no more than step_m apart within each segment: (lat, lon, length in
    metres of each piece between consecutive points, whether that piece was recorded rather
    than a jump across a segment break)."""
    lat, lon = track.lat, track.lon
    n = len(lat)
    if n < 2:
        return lat, lon, np.zeros(0), np.zeros(0, dtype=bool)
    leg_m = step_km(track) * M_PER_KM
    recorded = in_segment_steps(track)
    pieces = np.where(recorded, np.maximum(1, np.ceil(leg_m / step_m)), 1).astype(np.int64)
    leg = np.repeat(np.arange(n - 1), pieces)
    frac = (np.arange(len(leg)) - np.repeat(np.cumsum(pieces) - pieces, pieces)) / pieces[leg]
    plat, plon = along(lat[leg], lon[leg], lat[leg + 1], lon[leg + 1], frac)
    # the fixes themselves stay exact rather than going through the interpolation
    plat = np.r_[np.where(frac == 0, lat[leg], plat), lat[-1]]
    plon = np.r_[np.where(frac == 0, lon[leg], plon), lon[-1]]
    return plat, plon, leg_m[leg] / pieces[leg], recorded[leg]


# -- Fréchet ------------------------------------------------------------------------------------


def _discrete_frechet(pa, pb):
    """Discrete Fréchet distance (radians) between unit-vector sequences, by the classic DP
    c[i, j] = max(d(i, j), min(c[i-1, j], c[i, j-1], c[i-1, j-1])) swept by anti-diagonals
    i + j = k: every cell of one depends only on the two before it, so each is a single numpy
    step. It runs on squared chord length, which orders pairs exactly as distance does and is
    accurate at millimetres, and converts the answer to an angle at the end.

    Each diagonal lives in a buffer indexed by row + 1 (index 0 standing for row -1), padded with
    inf where the cell doesn't exist."""
    n, m = len(pa), len(pb)
    ax, ay, az = (np.ascontiguousarray(pa[:, c]) for c in range(3))
    # b reversed, so the cells of a diagonal (i up, j down) are contiguous in both
    bx, by, bz = (np.ascontiguousarray(pb[::-1, c]) for c in range(3))
    prev1, prev2 = np.full(n + 1, np.inf), np.full(n + 1, np.inf)  # diagonals k-1 and k-2
    for k in range(n + m - 1):
        lo, hi = max(0, k - m + 1), min(k, n - 1)
        rows, cols = slice(lo, hi + 1), slice(m - 1 - k + lo, m - k + hi)
        d2 = (ax[rows] - bx[cols]) ** 2 + (ay[rows] - by[cols]) ** 2 + (az[rows] - bz[cols]) ** 2
        if k:
            reach = np.minimum(np.minimum(prev1[lo : hi + 1], prev1[lo + 1 : hi + 2]), prev2[lo : hi + 1])
            d2 = np.maximum(d2, reach)
        prev2[lo + 1 : hi + 2] = d2  # diagonal k-2 is no longer needed: reuse its buffer
        prev2[lo] = np.inf  # row lo-1 isn't on this diagonal, whatever was left there
        prev1, prev2 = prev2, prev1
    return 2 * np.arcsin(min(1.0, np.sqrt(prev1[n]) / 2))
