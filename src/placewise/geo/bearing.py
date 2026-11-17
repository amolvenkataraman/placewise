"""Directions and movement on a sphere: bearings, destination points, points along a great circle,
distance from a path, and compass words. Distances in km, angles in degrees."""

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM

from ._arrays import as_floats, out, wrap_lon
from .distances import haversine


def initial_bearing(lat1, lon1, lat2, lon2):
    """Heading at the start of the great circle from point 1 to point 2: 0 = north, 90 = east."""
    lat1, lon1, lat2, lon2 = map(np.radians, as_floats(lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return out(np.degrees(np.arctan2(y, x)) % 360.0)


def final_bearing(lat1, lon1, lat2, lon2):
    """Heading on arrival at point 2 (differs from the initial one except along meridians and the equator)."""
    return out((np.asarray(initial_bearing(lat2, lon2, lat1, lon1)) + 180.0) % 360.0)


def destination(lat, lon, bearing, distance_km, radius_km=MEAN_RADIUS_KM):
    """(lat, lon) reached by travelling distance_km from (lat, lon) along the initial bearing."""
    lat, lon, bearing, dist = as_floats(lat, lon, bearing, distance_km)
    phi, lam, theta, delta = np.radians(lat), np.radians(lon), np.radians(bearing), dist / radius_km
    phi2 = np.arcsin(np.sin(phi) * np.cos(delta) + np.cos(phi) * np.sin(delta) * np.cos(theta))
    lam2 = lam + np.arctan2(
        np.sin(theta) * np.sin(delta) * np.cos(phi), np.cos(delta) - np.sin(phi) * np.sin(phi2)
    )
    return out(np.degrees(phi2)), out(wrap_lon(np.degrees(lam2)))


def along(lat1, lon1, lat2, lon2, fraction):
    """(lat, lon) at `fraction` (0..1, scalar or array) of the way along the great circle from
    point 1 to point 2. Spherical interpolation of unit vectors, so it works across poles and the
    antimeridian."""
    lat1, lon1, lat2, lon2, f = np.broadcast_arrays(*as_floats(lat1, lon1, lat2, lon2, fraction))
    (ax, ay, az), (bx, by, bz) = _unit_vector(lat1, lon1), _unit_vector(lat2, lon2)
    omega = np.arccos(np.clip(ax * bx + ay * by + az * bz, -1.0, 1.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        sin_omega = np.sin(omega)
        wa = np.where(sin_omega > 1e-15, np.sin((1 - f) * omega) / sin_omega, 1 - f)
        wb = np.where(sin_omega > 1e-15, np.sin(f * omega) / sin_omega, f)
    vx, vy, vz = wa * ax + wb * bx, wa * ay + wb * by, wa * az + wb * bz
    lat = np.degrees(np.arctan2(vz, np.hypot(vx, vy)))
    lon = np.degrees(np.arctan2(vy, vx))
    return out(lat), out(wrap_lon(lon))


def midpoint(lat1, lon1, lat2, lon2):
    """Halfway point on the great circle."""
    return along(lat1, lon1, lat2, lon2, 0.5)


def cross_track(lat1, lon1, lat2, lon2, lat3, lon3, radius_km=MEAN_RADIUS_KM):
    """Signed distance in km from point 3 to the great circle through points 1 and 2:
    negative to the left of the direction of travel, positive to the right."""
    delta13 = np.asarray(haversine(lat1, lon1, lat3, lon3, radius_km)) / radius_km
    theta13 = np.radians(initial_bearing(lat1, lon1, lat3, lon3))
    theta12 = np.radians(initial_bearing(lat1, lon1, lat2, lon2))
    return out(radius_km * np.arcsin(np.sin(delta13) * np.sin(theta13 - theta12)))


def along_track(lat1, lon1, lat2, lon2, lat3, lon3, radius_km=MEAN_RADIUS_KM):
    """Distance in km from point 1 to the closest point on the great circle (1 -> 2) to point 3."""
    delta13 = np.asarray(haversine(lat1, lon1, lat3, lon3, radius_km)) / radius_km
    xt = np.asarray(cross_track(lat1, lon1, lat2, lon2, lat3, lon3, radius_km)) / radius_km
    return out(radius_km * np.arccos(np.clip(np.cos(delta13) / np.cos(xt), -1.0, 1.0)))


_COMPASS = {
    4: ["N", "E", "S", "W"],
    8: ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
    16: ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"],
}


def compass(bearing, points=8):
    """Compass word for a bearing ("NE"), on a 4-, 8- or 16-point rose; arrays give string arrays."""
    if points not in _COMPASS:
        raise ValueError(f"points must be one of {sorted(_COMPASS)}")
    words = np.array(_COMPASS[points])
    sector = np.rint(np.asarray(bearing, dtype=np.float64) % 360.0 / (360.0 / points)).astype(int) % points
    result = words[sector]
    return str(result) if result.ndim == 0 else result


def _unit_vector(lat, lon):
    """(x, y, z) components of the unit vectors of same-shaped lat / lon arrays."""
    phi, lam = np.radians(lat), np.radians(lon)
    cos_phi = np.cos(phi)
    return cos_phi * np.cos(lam), cos_phi * np.sin(lam), np.sin(phi)
