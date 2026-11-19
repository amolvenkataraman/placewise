"""Map projections and grids on WGS84: UTM, UPS, MGRS, ECEF, local east-north-up frames and Web
Mercator. Coordinates are (lat, lon) degrees; projected and Cartesian values are metres.

UTM uses Karney's (2011) Krüger series to order n^6, accurate to about 5 nm within 3900 km of
the central meridian, so a whole zone and well beyond it. UTM covers -80 <= lat < 84; `to_utm`
refuses the polar caps rather than quietly returning a distorted grid, and `to_utm_ups` picks
UTM or UPS by the standard rule (zone 0 meaning UPS, as in GeographicLib). Other datums are out
of scope.
"""

from .ecef import aer, ecef_to_enu, enu_to_ecef, from_ecef, to_ecef
from .utm import from_mgrs, from_ups, from_utm, from_utm_ups, to_mgrs, to_ups, to_utm, to_utm_ups
from .web_mercator import from_web_mercator, to_web_mercator

__all__ = [
    "aer",
    "ecef_to_enu",
    "enu_to_ecef",
    "from_ecef",
    "from_mgrs",
    "from_ups",
    "from_utm",
    "from_utm_ups",
    "from_web_mercator",
    "to_ecef",
    "to_mgrs",
    "to_ups",
    "to_utm",
    "to_utm_ups",
    "to_web_mercator",
]
