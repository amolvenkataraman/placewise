"""Geographic toolkit: distances, bearings, shapes, coordinates, projections, grid codes and the sun.
Needs no data.

Coordinates are WGS84 degrees in (lat, lon) order; functions take scalars or numpy arrays and
broadcast; distances are km unless a name says otherwise (_m).
"""

from . import bearing, codes, coords, distances, lines, plus_codes, polylines, projections, shapes, sun, units
from .bearing import (
    along,
    along_track,
    compass,
    cross_track,
    destination,
    final_bearing,
    initial_bearing,
    midpoint,
)
from .codes import from_quadkey, geohash_decode, geohash_encode, quadkey, tile, tile_bounds
from .coords import format_decimal, format_dms, from_e7, from_exif, normalize_lon, parse, validate
from .distances import distance, equirectangular, geodesic, haversine
from .lines import nearest_point_on_polyline, nearest_point_on_segment, polyline_length, simplify
from .plus_codes import decode as plus_code_decode
from .plus_codes import encode as plus_code_encode
from .polygon_index import PolygonIndex
from .polylines import polyline_decode, polyline_encode
from .projections import (
    aer,
    ecef_to_enu,
    enu_to_ecef,
    from_ecef,
    from_mgrs,
    from_ups,
    from_utm,
    from_utm_ups,
    from_web_mercator,
    to_ecef,
    to_mgrs,
    to_ups,
    to_utm,
    to_utm_ups,
    to_web_mercator,
)
from .shapes import area, bbox_around, bbox_contains, bbox_split, contains
from .sun import SunTimes, sun_position, sun_times
from .units import convert

__all__ = [
    "PolygonIndex",
    "SunTimes",
    "aer",
    "along",
    "along_track",
    "area",
    "bbox_around",
    "bbox_contains",
    "bbox_split",
    "bearing",
    "codes",
    "compass",
    "contains",
    "convert",
    "coords",
    "cross_track",
    "destination",
    "distance",
    "distances",
    "ecef_to_enu",
    "enu_to_ecef",
    "equirectangular",
    "final_bearing",
    "format_decimal",
    "format_dms",
    "from_e7",
    "from_ecef",
    "from_exif",
    "from_mgrs",
    "from_quadkey",
    "from_ups",
    "from_utm",
    "from_utm_ups",
    "from_web_mercator",
    "geodesic",
    "geohash_decode",
    "geohash_encode",
    "haversine",
    "initial_bearing",
    "lines",
    "midpoint",
    "nearest_point_on_polyline",
    "nearest_point_on_segment",
    "normalize_lon",
    "parse",
    "plus_code_decode",
    "plus_code_encode",
    "plus_codes",
    "polyline_decode",
    "polyline_encode",
    "polyline_length",
    "polylines",
    "projections",
    "quadkey",
    "shapes",
    "simplify",
    "sun",
    "sun_position",
    "sun_times",
    "tile",
    "tile_bounds",
    "to_ecef",
    "to_mgrs",
    "to_ups",
    "to_utm",
    "to_utm_ups",
    "to_web_mercator",
    "units",
    "validate",
]
