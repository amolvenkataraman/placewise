"""Helpers the track operations share: ordering checks, segment membership, steps between
consecutive fixes, great-circle interpolation along steps and locating a boundary within a step."""

import numpy as np

from placewise.constants.track_ops import BOUNDARY_BISECTIONS
from placewise.geo.bearing import along
from placewise.geo.distances import haversine


def require_sorted(track):
    t = track.time
    if len(t) > 1 and not np.all(t[1:] >= t[:-1]):
        raise ValueError("track times must be non-decreasing; sort the track first")


def segment_ids(track):
    """Segment number of every point."""
    n = len(track)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    bounds = np.asarray((*track.segments, n))
    return np.repeat(np.arange(len(track.segments)), np.diff(bounds))


def in_segment_steps(track):
    """For each step k (fix k -> k + 1), whether both fixes belong to the same recording."""
    seg = segment_ids(track)
    return seg[1:] == seg[:-1]


def step_km(track):
    """Great-circle length of every step, segment breaks included."""
    lat, lon = track.lat, track.lon
    return np.asarray(haversine(lat[:-1], lon[:-1], lat[1:], lon[1:]), dtype=np.float64).reshape(-1)


def interpolate(track, i, j, f):
    """(lat, lon) a fraction f of the way from fix i to fix j along the great circle; fixes
    themselves are returned untouched so exact hits don't pick up round-trip error."""
    lat, lon = track.lat, track.lon
    i, j, f = np.asarray(i), np.asarray(j), np.asarray(f, dtype=np.float64)
    if i.size == 0 or len(lat) == 0:  # nothing to place; callers mask these as not ok
        return np.zeros(i.shape), np.zeros(i.shape)
    ilat, ilon = along(lat[i], lon[i], lat[j], lon[j], f)
    at_fix = (i == j) | (f == 0)
    return np.where(at_fix, lat[i], ilat), np.where(at_fix, lon[i], ilon)


def bisect_change(lat1, lon1, lat2, lon2, same):
    """Fraction along each great-circle step at which `same(lat, lon)` (True at the start, False
    at the end) first turns False, for many steps at once."""
    lo = np.zeros(len(lat1))
    hi = np.ones(len(lat1))
    for _ in range(BOUNDARY_BISECTIONS):
        mid = (lo + hi) / 2
        mlat, mlon = along(lat1, lon1, lat2, lon2, mid)
        still = np.asarray(same(np.atleast_1d(mlat), np.atleast_1d(mlon)), dtype=bool)
        lo = np.where(still, mid, lo)
        hi = np.where(still, hi, mid)
    return (lo + hi) / 2


def unit_vectors(lat, lon):
    phi, lam = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)], axis=-1)


def mean_position(lat, lon):
    """Centre of a cluster of points: the mean of their unit vectors, so it works across the
    antimeridian and near the poles."""
    v = unit_vectors(lat, lon).mean(axis=0)
    return float(np.degrees(np.arctan2(v[2], np.hypot(v[0], v[1])))), float(
        np.degrees(np.arctan2(v[1], v[0]))
    )
