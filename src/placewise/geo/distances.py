"""Distances between points. Pick by need: `equirectangular` for short hops in hot loops,
`haversine` (the default) for labels and thresholds, `geodesic` for reported numbers."""

import numpy as np

from placewise.constants import wgs84
from placewise.constants.earth import MEAN_RADIUS_KM

from ._arrays import as_floats, out, wrap_lon
from .units import convert


def haversine(lat1, lon1, lat2, lon2, radius_km=MEAN_RADIUS_KM):
    """Great-circle distance in km on a sphere. Up to ~0.5 % off the ellipsoid, stable for
    antipodal and coincident points (unlike the spherical law of cosines)."""
    lat1, lon1, lat2, lon2 = map(np.radians, as_floats(lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return out(2 * radius_km * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))))


def equirectangular(lat1, lon1, lat2, lon2, radius_km=MEAN_RADIUS_KM):
    """Flat-earth approximation in km: fastest, accurate for short hops (well under 0.1 % below
    ~10 km away from the poles), increasingly wrong over long distances."""
    lat1, lon1, lat2, lon2 = as_floats(lat1, lon1, lat2, lon2)
    x = np.radians(wrap_lon(lon2 - lon1)) * np.cos(np.radians((lat1 + lat2) / 2))
    y = np.radians(lat2 - lat1)
    return out(radius_km * np.hypot(x, y))


def geodesic(lat1, lon1, lat2, lon2):
    """Shortest distance in km on the WGS84 ellipsoid (Karney's algorithm, via GeographicLib):
    nanometre-level accuracy, including antipodal points where Vincenty's method fails."""
    try:
        from geographiclib.geodesic import Geodesic
    except ImportError:
        raise ImportError("geodesic distances need GeographicLib: pip install placewise[geodesic]") from None
    ellipsoid = Geodesic(wgs84.A_M, wgs84.F)
    lat1, lon1, lat2, lon2 = np.broadcast_arrays(*as_floats(lat1, lon1, lat2, lon2))
    metres = np.fromiter(
        (
            ellipsoid.Inverse(a, b, c, d, Geodesic.DISTANCE)["s12"]
            for a, b, c, d in zip(lat1.ravel(), lon1.ravel(), lat2.ravel(), lon2.ravel(), strict=True)
        ),
        dtype=np.float64,
        count=lat1.size,
    )
    return out(metres.reshape(lat1.shape) / 1000.0)


_METHODS = {"haversine": haversine, "fast": equirectangular, "geodesic": geodesic}


def distance(lat1, lon1, lat2, lon2, method="haversine", units="km"):
    """Distance between points: method "haversine" (default), "fast" (equirectangular) or
    "geodesic" (WGS84); units any length unit `units.convert` knows."""
    try:
        fn = _METHODS[method]
    except KeyError:
        raise ValueError(f"unknown method {method!r}; use one of {', '.join(_METHODS)}") from None
    km = fn(lat1, lon1, lat2, lon2)
    return km if units == "km" else out(convert(km, "km", units))
