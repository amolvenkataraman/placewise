"""Web Mercator (EPSG:3857), the projection of web map tiles."""

import numpy as np

from placewise.constants.web_mercator import MAX_LAT as _MERCATOR_MAX_LAT
from placewise.constants.wgs84 import A_M

from .._arrays import as_floats, out


def to_web_mercator(lat, lon):
    """EPSG:3857 (x, y) metres. Latitude is clamped to the projection's limit (about 85.05
    degrees); longitude is not wrapped, so 180 gives x = pi * a."""
    lat, lon = as_floats(lat, lon)
    phi = np.radians(np.clip(lat, -_MERCATOR_MAX_LAT, _MERCATOR_MAX_LAT))
    # EPSG:3857 is spherical Mercator on a sphere of radius a, applied to WGS84 coordinates
    return out(A_M * np.radians(lon)), out(A_M * np.arcsinh(np.tan(phi)))


def from_web_mercator(x, y):
    """(lat, lon) of EPSG:3857 metres."""
    x, y = as_floats(x, y)
    return out(np.degrees(np.arctan(np.sinh(y / A_M)))), out(np.degrees(x / A_M))
