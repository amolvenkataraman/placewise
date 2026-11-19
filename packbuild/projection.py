"""Map projections the build unprojects from, with numpy: Lambert Conformal Conic (two standard
parallels) on an ellipsoid, and Mollweide on a sphere (the GHSL grids, below).

Statistics Canada publishes its boundary files only in "Statistics Canada Lambert" (EPSG:3347,
NAD83), and placewise's runtime reads longitude/latitude only, so the build unprojects them here.
Formulas: IOGP Guidance Note 7-2 ("Coordinate Conversions and Transformations including Formulas"),
section 3.2.1.1, Lambert Conic Conformal (2SP), EPSG method 9802.

Datum: the output is NAD83 longitude/latitude. NAD83 (and its realisation NAD83(CSRS)) differs
from WGS84 by about 1 to 2 m across Canada today, far below the generalisation of the boundaries,
so no datum shift is applied and the result is used as WGS84.
"""

import math
from dataclasses import dataclass

import numpy as np

GRS80_A = 6378137.0
GRS80_INV_F = 298.257222101


@dataclass(frozen=True)
class LambertConformalConic:
    """EPSG method 9802. Angles in degrees, distances in the units of `a` and the false origin."""

    lat_origin: float  # latitude of false origin
    lon_origin: float  # longitude of false origin (central meridian)
    lat_1: float  # standard parallels
    lat_2: float
    false_easting: float = 0.0
    false_northing: float = 0.0
    a: float = GRS80_A
    inv_f: float = GRS80_INV_F

    def __post_init__(self):
        f = 1.0 / self.inv_f
        e = math.sqrt(2 * f - f * f)
        p1, p2, p0 = (math.radians(v) for v in (self.lat_1, self.lat_2, self.lat_origin))
        m1, m2 = self._m(p1, e), self._m(p2, e)
        t1, t2, t0 = self._t(p1, e), self._t(p2, e), self._t(p0, e)
        # with one standard parallel, n is the limit of the general formula: sin(lat_1)
        n = math.sin(p1) if p1 == p2 else (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
        big_f = m1 / (n * t1**n)
        constants = {"_e": e, "_n": n, "_af": self.a * big_f, "_r0": self.a * big_f * t0**n}
        for name, value in constants.items():
            object.__setattr__(self, name, value)

    @staticmethod
    def _m(phi, e):
        return np.cos(phi) / np.sqrt(1 - (e * np.sin(phi)) ** 2)

    @staticmethod
    def _t(phi, e):
        es = e * np.sin(phi)
        return np.tan(np.pi / 4 - phi / 2) / ((1 - es) / (1 + es)) ** (e / 2)

    def forward(self, lon, lat):
        """(easting, northing) for longitude/latitude in degrees (scalars or arrays)."""
        phi = np.radians(np.asarray(lat, dtype=np.float64))
        theta = self._n * np.radians(np.asarray(lon, dtype=np.float64) - self.lon_origin)
        r = self._af * self._t(phi, self._e) ** self._n
        return self.false_easting + r * np.sin(theta), self.false_northing + self._r0 - r * np.cos(theta)

    def inverse(self, x, y, tol=1e-12, max_iter=15):
        """(longitude, latitude) in degrees for easting/northing (scalars or arrays)."""
        dx = np.asarray(x, dtype=np.float64) - self.false_easting
        dy = self._r0 - (np.asarray(y, dtype=np.float64) - self.false_northing)
        sign = 1.0 if self._n > 0 else -1.0
        r = sign * np.hypot(dx, dy)
        t = (r / self._af) ** (1 / self._n)
        theta = np.arctan2(sign * dx, sign * dy)
        e = self._e
        phi = np.pi / 2 - 2 * np.arctan(t)
        for _ in range(max_iter):
            es = e * np.sin(phi)
            nxt = np.pi / 2 - 2 * np.arctan(t * ((1 - es) / (1 + es)) ** (e / 2))
            done = np.max(np.abs(nxt - phi)) < tol if np.size(nxt) else True
            phi = nxt
            if done:
                break
        lon = np.degrees(theta / self._n) + self.lon_origin
        return lon, np.degrees(phi)

    def inverse_rings(self, x, y, offsets, tol=1e-12, max_iter=15):
        """`inverse` of many rings at once, ring k being x[offsets[k]:offsets[k + 1]]: the same
        numbers as calling `inverse` on each ring, since each ring stops iterating when its own
        largest step is below tol, as a call on it alone would."""
        x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
        offsets = np.asarray(offsets, dtype=np.int64)
        dx = x - self.false_easting
        dy = self._r0 - (y - self.false_northing)
        sign = 1.0 if self._n > 0 else -1.0
        r = sign * np.hypot(dx, dy)
        t = (r / self._af) ** (1 / self._n)
        theta = np.arctan2(sign * dx, sign * dy)
        e = self._e
        phi = np.pi / 2 - 2 * np.arctan(t)
        active = np.flatnonzero(np.diff(offsets) > 0)  # an empty ring is done at once
        for _ in range(max_iter):
            if not len(active):
                break
            sizes = offsets[active + 1] - offsets[active]
            first = np.cumsum(sizes) - sizes  # each active ring's start among the active vertices
            idx = np.repeat(offsets[active] - first, sizes) + np.arange(int(sizes.sum()))
            es = e * np.sin(phi[idx])
            nxt = np.pi / 2 - 2 * np.arctan(t[idx] * ((1 - es) / (1 + es)) ** (e / 2))
            step = np.maximum.reduceat(np.abs(nxt - phi[idx]), first)
            phi[idx] = nxt
            active = active[~(step < tol)]
        lon = np.degrees(theta / self._n) + self.lon_origin
        return lon, np.degrees(phi)


# EPSG:3347 "NAD83 / Statistics Canada Lambert": the projection of every 2021 Census boundary file
# (Boundary Files Reference Guide 2021, 92-160-G, "Geographic representation"). The central
# meridian is 91°52'W, which the guide rounds to -91.866667.
STATCAN_LAMBERT = LambertConformalConic(
    lat_origin=63.390675,
    lon_origin=-(91 + 52 / 60),
    lat_1=49.0,
    lat_2=77.0,
    false_easting=6200000.0,
    false_northing=3000000.0,
)


@dataclass(frozen=True)
class Mollweide:
    """Mollweide (equal-area pseudocylindrical) on a sphere of radius `radius`, forward and inverse.

    Formulas: Snyder, "Map Projections: A Working Manual" (USGS PP 1395, 1987), pp. 249-252. The
    forward needs the auxiliary angle theta of 2 theta + sin 2 theta = pi sin(lat), found by
    Newton's method; the inverse is closed-form. Points outside the projection's ellipse come back
    with a longitude beyond +-180 (clipped there) and latitude +-90 at most."""

    radius: float = GRS80_A
    lon_origin: float = 0.0
    false_easting: float = 0.0
    false_northing: float = 0.0

    def forward(self, lon, lat, tol=1e-12, max_iter=50):
        """(easting, northing) for longitude/latitude in degrees (scalars or arrays)."""
        phi = np.radians(np.asarray(lat, dtype=np.float64))
        lam = np.radians(np.asarray(lon, dtype=np.float64) - self.lon_origin)
        target = np.pi * np.sin(phi)
        t = np.array(phi, dtype=np.float64)  # 2 theta, iterated from 2 theta = phi
        for _ in range(max_iter):
            with np.errstate(divide="ignore", invalid="ignore"):
                step = (t + np.sin(t) - target) / (1 + np.cos(t))
            step = np.where(np.isfinite(step), step, 0.0)  # at the poles 1 + cos(t) is 0: done
            t = t - step
            if not np.size(step) or np.max(np.abs(step)) < tol:
                break
        theta = np.where(np.abs(phi) >= np.pi / 2, np.sign(phi) * np.pi / 2, t / 2)
        x = 2 * np.sqrt(2) / np.pi * self.radius * lam * np.cos(theta)
        y = np.sqrt(2) * self.radius * np.sin(theta)
        return self.false_easting + x, self.false_northing + y

    def inverse(self, x, y):
        """(longitude, latitude) in degrees for easting/northing (scalars or arrays)."""
        x = np.asarray(x, dtype=np.float64) - self.false_easting
        y = np.asarray(y, dtype=np.float64) - self.false_northing
        theta = np.arcsin(np.clip(y / (np.sqrt(2) * self.radius), -1.0, 1.0))
        phi = np.arcsin(np.clip((2 * theta + np.sin(2 * theta)) / np.pi, -1.0, 1.0))
        with np.errstate(divide="ignore", invalid="ignore"):
            lam = np.pi * x / (2 * np.sqrt(2) * self.radius * np.cos(theta))
        lam = np.where(np.isfinite(lam), lam, 0.0)
        lon = np.clip(np.degrees(lam) + self.lon_origin, -180.0, 180.0)
        return lon, np.degrees(phi)


# ESRI:54009 "World_Mollweide": the GHSL grids' projection (GHS-SMOD, GHS-POP), applied by Esri and
# GDAL to the sphere of WGS84's semi-major axis (6378137 m), central meridian 0, no false origin.
WORLD_MOLLWEIDE = Mollweide()
