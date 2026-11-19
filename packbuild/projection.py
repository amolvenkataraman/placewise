"""Map projections on an ellipsoid, forward and inverse, with numpy: the build unprojects
publishers' files here, since placewise's runtime reads longitude/latitude only. Formulas: IOGP
Guidance Note 7-2 ("Coordinate Conversions and Transformations including Formulas").

- Lambert Conformal Conic (2SP), EPSG method 9802 (GN 7-2 3.2.1.1): Statistics Canada publishes
  its boundary files only in "Statistics Canada Lambert" (EPSG:3347, NAD83). NAD83 (and its
  realisation NAD83(CSRS)) differs from WGS84 by about 1 to 2 m across Canada today, far below the
  generalisation of the boundaries, so no datum shift is applied and the result is used as WGS84.
- Lambert Azimuthal Equal Area, EPSG method 9820 (GN 7-2 3.3.2): the EEA publishes European data
  in ETRS89-LAEA (EPSG:3035). ETRS89 moves with the Eurasian plate and is about 0.7 m from WGS84
  (ITRF) today, again far below the generalisation, so it too is used as WGS84.
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
class LambertAzimuthalEqualArea:
    """EPSG method 9820 (oblique aspect). Angles in degrees, distances in the units of `a`; on a
    sphere (inv_f = inf) the authalic latitude is the latitude itself."""

    lat_origin: float  # latitude of natural origin
    lon_origin: float  # longitude of natural origin
    false_easting: float = 0.0
    false_northing: float = 0.0
    a: float = GRS80_A
    inv_f: float = GRS80_INV_F

    def __post_init__(self):
        f = 0.0 if math.isinf(self.inv_f) else 1.0 / self.inv_f
        e = math.sqrt(2 * f - f * f)
        q_p = self._q(math.pi / 2, e)
        p0 = math.radians(self.lat_origin)
        beta0 = math.asin(self._q(p0, e) / q_p)
        rq = self.a * math.sqrt(q_p / 2)
        d = self.a * math.cos(p0) / math.sqrt(1 - (e * math.sin(p0)) ** 2) / (rq * math.cos(beta0))
        e2 = e * e
        series = (  # authalic latitude -> latitude (GN 7-2 3.3.2, inverse)
            e2 / 3 + 31 * e2**2 / 180 + 517 * e2**3 / 5040,
            23 * e2**2 / 360 + 251 * e2**3 / 3780,
            761 * e2**3 / 45360,
        )
        constants = {"_e": e, "_qp": q_p, "_rq": rq, "_d": d, "_beta0": beta0, "_series": series}
        for name, value in constants.items():
            object.__setattr__(self, name, value)

    @staticmethod
    def _q(phi, e):
        s = np.sin(phi)
        if e == 0:
            return 2 * s
        return (1 - e * e) * (s / (1 - (e * s) ** 2) - np.log((1 - e * s) / (1 + e * s)) / (2 * e))

    def forward(self, lon, lat):
        """(easting, northing) for longitude/latitude in degrees (scalars or arrays)."""
        phi = np.radians(np.asarray(lat, dtype=np.float64))
        dlon = np.radians(np.asarray(lon, dtype=np.float64) - self.lon_origin)
        beta = np.arcsin(np.clip(self._q(phi, self._e) / self._qp, -1.0, 1.0))
        sb0, cb0 = math.sin(self._beta0), math.cos(self._beta0)
        b = self._rq * np.sqrt(2 / (1 + sb0 * np.sin(beta) + cb0 * np.cos(beta) * np.cos(dlon)))
        x = self.false_easting + b * self._d * np.cos(beta) * np.sin(dlon)
        y = self.false_northing + (b / self._d) * (cb0 * np.sin(beta) - sb0 * np.cos(beta) * np.cos(dlon))
        return x, y

    def inverse(self, x, y):
        """(longitude, latitude) in degrees for easting/northing (scalars or arrays)."""
        dx = np.asarray(x, dtype=np.float64) - self.false_easting
        dy = np.asarray(y, dtype=np.float64) - self.false_northing
        d = self._d
        rho = np.hypot(dx / d, d * dy)
        c = 2 * np.arcsin(np.clip(rho / (2 * self._rq), -1.0, 1.0))
        sb0, cb0 = math.sin(self._beta0), math.cos(self._beta0)
        sc, cc = np.sin(c), np.cos(c)
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = np.arcsin(np.clip(cc * sb0 + np.where(rho > 0, d * dy * sc * cb0 / rho, 0.0), -1.0, 1.0))
        s1, s2, s3 = self._series
        phi = beta + s1 * np.sin(2 * beta) + s2 * np.sin(4 * beta) + s3 * np.sin(6 * beta)
        lam = np.arctan2(dx * sc, d * rho * cb0 * cc - d * d * dy * sb0 * sc)
        return np.degrees(lam) + self.lon_origin, np.degrees(phi)


# EPSG:3035 "ETRS89-extended / LAEA Europe" (GN 7-2 3.3.2's example): the EEA's European datasets
ETRS89_LAEA = LambertAzimuthalEqualArea(
    lat_origin=52.0, lon_origin=10.0, false_easting=4321000.0, false_northing=3210000.0
)
