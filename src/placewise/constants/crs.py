"""Every coordinate reference system and grid placewise reads or writes: official EPSG name, the
names people actually use, and the EPSG code where one exists. All are WGS84-based; other datums and
obfuscated systems (GCJ-02, BD-09) are out of scope by design."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CRS:
    key: str
    name: str  # official EPSG name, or a descriptive one where EPSG has no entry
    common_names: tuple[str, ...]
    epsg: int | None  # None: not a CRS in the EPSG registry (grids, encodings, local frames)
    note: str = ""


WGS84_2D = CRS(
    "wgs84",
    "WGS 84",
    ("WGS84", "lat/lon", "GPS coordinates", "geographic"),
    4326,
    "Latitude/longitude in degrees; what GPS, phones and EXIF record. EPSG axis order is lat, lon.",
)
WGS84_3D = CRS(
    "wgs84_3d",
    "WGS 84",
    ("WGS84 3D", "lat/lon/height"),
    4979,
    "As 4326 plus height above the ellipsoid in metres (GPS altitude before geoid correction).",
)
ECEF = CRS(
    "ecef",
    "WGS 84",
    ("ECEF", "Earth-centred Earth-fixed", "geocentric"),
    4978,
    "X, Y, Z metres from the Earth's centre; EPSG lists it as the geocentric WGS 84 CRS.",
)
WEB_MERCATOR = CRS(
    "web_mercator",
    "WGS 84 / Pseudo-Mercator",
    ("Web Mercator", "Google Mercator", "Spherical Mercator", "EPSG:900913"),
    3857,
    "Metres on the projection used by OSM-style map tiles; undefined beyond about ±85.05°.",
)
UTM = CRS(
    "utm",
    "WGS 84 / UTM zone {zone}{hemisphere}",
    ("UTM", "Universal Transverse Mercator"),
    None,
    "One CRS per zone and hemisphere: EPSG 32601-32660 north, 32701-32760 south (see utm_epsg).",
)
UPS_NORTH = CRS(
    "ups_north",
    "WGS 84 / UPS North (E,N)",
    ("UPS North", "Universal Polar Stereographic"),
    5041,
    "North of 84°N. EPSG:32661 is the same projection with northing-first axis order.",
)
UPS_SOUTH = CRS(
    "ups_south",
    "WGS 84 / UPS South (E,N)",
    ("UPS South", "Universal Polar Stereographic"),
    5042,
    "South of 80°S. EPSG:32761 is the same projection with northing-first axis order.",
)
MGRS = CRS(
    "mgrs",
    "Military Grid Reference System",
    ("MGRS", "USNG (in the US)"),
    None,
    "Alphanumeric grid references built on UTM/UPS (zone, band, 100 km square, digits); not a CRS.",
)
ENU = CRS(
    "enu",
    "Local East-North-Up",
    ("ENU", "local tangent plane", "NED", "AER"),
    None,
    "Topocentric frame around a chosen origin; defined per use, so no single EPSG code.",
)
SPHERE = CRS(
    "sphere",
    "IUGG mean-radius sphere",
    ("spherical Earth", "haversine sphere"),
    None,
    "Radius 6371.0088 km; the model behind haversine and the spherical bearing functions.",
)
PLUS_CODE = CRS(
    "plus_code",
    "Open Location Code",
    ("plus codes", "OLC"),
    None,
    "Encoding of WGS 84 coordinates, e.g. 8FVC9G8F+6X (the spec's Zurich example).",
)
GEOHASH = CRS("geohash", "Geohash", ("geohash",), None, "Encoding of WGS 84 coordinates.")
WEB_TILES = CRS(
    "web_tiles",
    "Web map tiles (z/x/y) and quadkeys",
    ("slippy map tiles", "XYZ tiles", "quadkey"),
    None,
    "Tile indices on Web Mercator (EPSG:3857).",
)
EGM2008_HEIGHT = CRS(
    "egm2008",
    "EGM2008 height",
    ("height above sea level", "orthometric height"),
    3855,
    "Vertical datum of Copernicus elevation data; differs from GPS ellipsoid height by up to ~100 m.",
)

ALL = (
    WGS84_2D,
    WGS84_3D,
    ECEF,
    WEB_MERCATOR,
    UTM,
    UPS_NORTH,
    UPS_SOUTH,
    MGRS,
    ENU,
    SPHERE,
    PLUS_CODE,
    GEOHASH,
    WEB_TILES,
    EGM2008_HEIGHT,
)


def utm_epsg(zone, hemisphere):
    """EPSG code of a WGS 84 UTM zone: 326zz north, 327zz south."""
    if not 1 <= zone <= 60 or hemisphere not in ("N", "S"):
        raise ValueError(f"no UTM zone {zone}{hemisphere}; zones are 1-60, hemisphere N or S")
    return (32600 if hemisphere == "N" else 32700) + zone
