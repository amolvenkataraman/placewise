"""Earth-centred, Earth-fixed (ECEF) coordinates on WGS84 and local east-north-up frames: to and
from ECEF, between ECEF and a local frame, and azimuth, elevation and range between two points."""

import numpy as np

from placewise.constants.wgs84 import A_M, E2

from .._arrays import as_floats, out

_E4 = E2 * E2


def to_ecef(lat, lon, h_m=0):
    """Earth-centred, Earth-fixed (x, y, z) in metres; h_m is height above the ellipsoid."""
    return tuple(out(v) for v in _to_ecef(*as_floats(lat, lon, h_m)))


def from_ecef(x, y, z):
    """(lat, lon, h_m) from ECEF metres, by Vermeille's closed form (2011 revision, as in
    GeographicLib), which stays exact everywhere including deep inside the Earth."""
    x, y, z = np.broadcast_arrays(*as_floats(x, y, z))
    r = np.hypot(x, y)
    p = (r / A_M) ** 2
    q = (1 - E2) * (z / A_M) ** 2
    rr = (p + q - _E4) / 6
    with np.errstate(divide="ignore", invalid="ignore"):
        s = _E4 * p * q / 4
        r2, r3 = rr * rr, rr**3
        disc = s * (2 * r3 + s)
        t3 = s + r3
        t3 = t3 + np.where(t3 < 0, -1.0, 1.0) * np.sqrt(np.maximum(disc, 0.0))
        t = np.cbrt(t3)
        u_cubic = rr + t + np.where(t != 0, r2 / np.where(t != 0, t, 1.0), 0.0)
        u_trig = rr + 2 * rr * np.cos(np.arctan2(np.sqrt(np.maximum(-disc, 0.0)), -(s + r3)) / 3)
        u = np.where(disc >= 0, u_cubic, u_trig)
        v = np.sqrt(u * u + _E4 * q)
        uv = np.where(u < 0, _E4 * q / (v - u), u + v)  # avoids cancellation when u < 0
        w = np.maximum(0.0, E2 * (uv - q) / (2 * v))
        k = uv / (np.sqrt(uv + w * w) + w)
        d = k * r / (k + E2)
        lat = np.degrees(np.arctan2(z / k, r / (k + E2)))
        h = (1 - (1 - E2) / k) * np.hypot(d, z)
    # on the equatorial plane inside the evolute (|r| <= e^2 a) the general formula is 0/0;
    # take its limit instead
    inner = (_E4 * q == 0) & (rr <= 0)
    zz = np.sqrt(np.maximum(_E4 - p, 0.0) / (1 - E2))
    xx = np.sqrt(p)
    lat = np.where(inner, np.degrees(np.arctan2(np.copysign(zz, z), xx)), lat)
    h = np.where(inner, -A_M * (1 - E2) * np.hypot(zz, xx) / E2, h)
    return out(lat), out(np.degrees(np.arctan2(y, x))), out(h)


def ecef_to_enu(x, y, z, lat0, lon0, h0=0):
    """(east, north, up) metres of an ECEF point relative to the observer at (lat0, lon0, h0)."""
    return tuple(out(v) for v in _ecef_to_enu(*as_floats(x, y, z, lat0, lon0, h0)))


def enu_to_ecef(east, north, up, lat0, lon0, h0=0):
    """ECEF (x, y, z) metres of a point given as (east, north, up) from (lat0, lon0, h0)."""
    east, north, up, lat0, lon0, h0 = as_floats(east, north, up, lat0, lon0, h0)
    sp, cp, sl, cl = _sincos(lat0, lon0)
    x0, y0, z0 = _to_ecef(lat0, lon0, h0)
    x = x0 - sl * east - sp * cl * north + cp * cl * up
    y = y0 + cl * east - sp * sl * north + cp * sl * up
    z = z0 + cp * north + sp * up
    return out(x), out(y), out(z)


def aer(lat0, lon0, h0, lat, lon, h):
    """(azimuth_deg from north, elevation_deg above the observer's horizon, slant_range_m) of
    (lat, lon, h) seen from (lat0, lon0, h0); heights in metres above the ellipsoid."""
    lat0, lon0, h0, lat, lon, h = as_floats(lat0, lon0, h0, lat, lon, h)
    east, north, up = _ecef_to_enu(*_to_ecef(lat, lon, h), lat0, lon0, h0)
    horizontal = np.hypot(east, north)
    azimuth = np.degrees(np.arctan2(east, north)) % 360.0
    elevation = np.degrees(np.arctan2(up, horizontal))
    return out(azimuth), out(elevation), out(np.hypot(horizontal, up))


def _to_ecef(lat, lon, h):
    sp, cp, sl, cl = _sincos(lat, lon)
    n = A_M / np.sqrt(1 - E2 * sp * sp)  # prime-vertical radius of curvature
    return (n + h) * cp * cl, (n + h) * cp * sl, (n * (1 - E2) + h) * sp


def _ecef_to_enu(x, y, z, lat0, lon0, h0):
    sp, cp, sl, cl = _sincos(lat0, lon0)
    x0, y0, z0 = _to_ecef(lat0, lon0, h0)
    dx, dy, dz = x - x0, y - y0, z - z0
    east = -sl * dx + cl * dy
    north = -sp * cl * dx - sp * sl * dy + cp * dz
    up = cp * cl * dx + cp * sl * dy + sp * dz
    return east, north, up


def _sincos(lat, lon):
    phi, lam = np.radians(lat), np.radians(lon)
    return np.sin(phi), np.cos(phi), np.sin(lam), np.cos(lam)
