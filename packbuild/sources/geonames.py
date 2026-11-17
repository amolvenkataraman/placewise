"""GeoNames (CC BY 4.0): the `cities` point layer from cities1000 (places with 1,000+ people).

GeoNames dumps are UTF-8, tab-separated, one record per line, with no quoting and no escaping, so
they are split on tabs only (the csv module would mangle names that contain quotes).

Future work: the `alternatenames` field (and alternateNamesV2) is left out of the world pack for
size; only its count is kept. Names in other languages belong in a later, optional names pack.
"""

import logging
from collections import Counter

from ..layer import LayerData

SOURCE = "geonames"

# https://download.geonames.org/export/dump/readme.txt, "The main 'geoname' table"
GEONAME_FIELDS = (
    "geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude", "feature_class",
    "feature_code", "country_code", "cc2", "admin1_code", "admin2_code", "admin3_code", "admin4_code",
    "population", "elevation", "dem", "timezone", "modification_date",
)  # fmt: skip
CITY_COLUMNS = (
    "id", "name", "asciiname", "country", "admin1", "admin1_name", "feature_code", "population",
    "elevation", "timezone", "alternate_count",
)  # fmt: skip
ELEVATION_NULL = -32768  # i2 sentinel
_DEM_NO_DATA = -9999
_I2_MAX = 32767

log = logging.getLogger(__name__)


def read_tsv(path, columns, comments=False, exact=True):
    """Rows of a GeoNames dump as lists of strings. `columns` is the expected field count (the
    minimum when `exact` is false); a row that doesn't fit is an error naming its line."""
    with open(path, encoding="utf-8", newline="") as f:
        for number, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line or (comments and line.startswith("#")):
                continue
            row = line.split("\t")
            if len(row) < columns or (exact and len(row) != columns):
                raise ValueError(f"{path}: line {number} has {len(row)} fields, expected {columns}")
            yield row


def read_admin1(path):
    """{"CA.08": "Ontario", ...} from admin1CodesASCII.txt (code, name, ascii name, geonameid)."""
    return {row[0]: row[1] for row in read_tsv(path, 4, exact=False)}


def read_country_info(path):
    """{"CA": "Canada", ...} from countryInfo.txt (ISO, ISO3, ISO-Numeric, fips, Country, ...)."""
    return {row[0]: row[4] for row in read_tsv(path, 5, comments=True, exact=False)}


def cities(cities_path, admin1_path, country_info_path=None):
    """The cities layer. admin1_name is joined from admin1CodesASCII ("" when GeoNames has no entry
    for the code); elevation is the surveyed one, else the DEM's, else null. countryInfo, when
    given, is used to report city country codes GeoNames itself doesn't list."""
    admin1_names = read_admin1(admin1_path)
    cols = {name: [] for name in CITY_COLUMNS}
    lat, lon = [], []
    for row in read_tsv(cities_path, len(GEONAME_FIELDS)):
        r = dict(zip(GEONAME_FIELDS, row, strict=True))
        country, admin1 = r["country_code"], r["admin1_code"]
        cols["id"].append(f"geonames:{r['geonameid']}")
        cols["name"].append(r["name"])
        cols["asciiname"].append(r["asciiname"])
        cols["country"].append(country)
        cols["admin1"].append(admin1)
        cols["admin1_name"].append(admin1_names.get(f"{country}.{admin1}", ""))
        cols["feature_code"].append(r["feature_code"])
        cols["population"].append(int(r["population"] or 0))
        cols["elevation"].append(_elevation(r["elevation"], r["dem"]))
        cols["timezone"].append(r["timezone"])
        names = [n for n in r["alternatenames"].split(",") if n]
        cols["alternate_count"].append(min(len(names), _I2_MAX))
        lat.append(float(r["latitude"]))
        lon.append(float(r["longitude"]))
    if country_info_path is not None:
        known = read_country_info(country_info_path)
        unknown = Counter(c for c in cols["country"] if c not in known)
        if unknown:
            log.warning("cities with country codes not in countryInfo: %s", dict(unknown))
    types = {name: "str" for name in cols}
    types.update(population="i8", elevation="i2", alternate_count="i2")
    return LayerData(
        "cities",
        "point",
        cols,
        (SOURCE,),
        lat=lat,
        lon=lon,
        types=types,
        nulls={"elevation": ELEVATION_NULL},
    )


def _elevation(surveyed, dem):
    for value in (surveyed, dem):
        if value.strip():
            metres = int(float(value))
            if metres != _DEM_NO_DATA:
                return max(min(metres, _I2_MAX), ELEVATION_NULL + 1)
    return ELEVATION_NULL
