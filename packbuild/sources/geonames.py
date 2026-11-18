"""GeoNames (CC BY 4.0): the `cities` point layer from cities1000 (places with 1,000+ people), and
the country facts (countryInfo.txt, timeZones.txt) the country profiles are built from.

GeoNames dumps are UTF-8, tab-separated, one record per line, with no quoting and no escaping, so
they are split on tabs only (the csv module would mangle names that contain quotes).

alternateNamesV2 (`read_alternate_names`, `pick_alternates`) gives the world pack's aliases the
names location strings use: English names, abbreviations, IATA codes and short names, plus former
names a curated dataset confirms (GeoNames' flags are often wrong, so `isHistoric` alone isn't
trusted). Names in other languages belong in a later, optional names pack.
"""

import io
import logging
import re
import zipfile
from collections import Counter
from dataclasses import dataclass

from placewise.constants._keys import city_key

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
# countryInfo.txt columns, as its header names them
COUNTRY_INFO_FIELDS = (
    "iso", "iso3", "iso_numeric", "fips", "country", "capital", "area", "population", "continent",
    "tld", "currency_code", "currency_name", "phone", "postal_code_format", "postal_code_regex",
    "languages", "geonameid", "neighbours", "equivalent_fips_code",
)  # fmt: skip
# alternateNamesV2.txt columns (readme, "The table 'alternate names'")
ALTERNATE_FIELDS = (
    "alternate_id", "geonameid", "language", "name", "preferred", "short", "colloquial", "historic",
    "from", "to",
)  # fmt: skip
ALTERNATE_MEMBER = "alternateNamesV2.txt"
# the pseudo-languages and languages kept: English, abbreviations, IATA codes, no language given
_LANGUAGES = frozenset(("en", "abbr", "iata", ""))
HISTORIC_MIN_POPULATION = 100_000  # a city's former names are kept only from this size up
_ALTERNATE_MAX = 60  # characters; longer "names" are descriptions
_INVISIBLE = re.compile(r"[\u0000-\u001f\u007f\u00ad\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff|]")
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


def read_country_facts(path):
    """{"CA": {field: text}} from countryInfo.txt, every COUNTRY_INFO_FIELDS column stripped of
    surrounding space ("" where GeoNames has no value)."""
    width = len(COUNTRY_INFO_FIELDS)
    return {
        row[0]: dict(zip(COUNTRY_INFO_FIELDS, (v.strip() for v in row[:width]), strict=True))
        for row in read_tsv(path, width, comments=True, exact=False)
    }


def read_time_zones(path):
    """{"CA": ("America/St_Johns", ...)} from timeZones.txt (CountryCode, TimeZoneId, offsets), in
    file order; the header row is skipped."""
    zones = {}
    for row in read_tsv(path, 2, exact=False):
        if row[0] != "CountryCode":
            zones.setdefault(row[0], []).append(row[1])
    return {code: tuple(ids) for code, ids in zones.items()}


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


@dataclass(frozen=True, slots=True)
class AlternateName:
    language: str  # ISO 639 code, or "abbr", "iata", "" (none given)
    name: str
    preferred: bool
    short: bool
    colloquial: bool
    historic: bool


def read_alternate_names(path, wanted):
    """{geonameid: [AlternateName]} for the ids in `wanted` (ints), in file order, from
    alternateNamesV2.zip (streamed, never extracted: the text file is ~800 MB) or its .txt.
    Only the languages a pack keeps are returned (links, postal codes, Wikidata ids are not)."""
    wanted = {str(g) for g in wanted}
    found = {}
    with _open_alternates(path) as f:
        for line in f:
            row = line.rstrip("\r\n").split("\t")
            if len(row) < 8 or row[1] not in wanted or row[2] not in _LANGUAGES:
                continue
            flags = [v == "1" for v in row[4:8]]
            found.setdefault(int(row[1]), []).append(AlternateName(row[2], row[3].strip(), *flags))
    return found


def _open_alternates(path):
    if str(path).endswith(".zip"):
        archive = zipfile.ZipFile(path)
        return io.TextIOWrapper(archive.open(ALTERNATE_MEMBER), encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")


def pick_alternates(names, *, population=0, formers=frozenset(), codes=True):
    """The (name, kind) pairs of one feature's alternate names a pack keeps, best first:
    abbreviations ("abbr"), IATA codes ("code", only with `codes`), English short names ("short",
    even when flagged colloquial: "LA"), other English names ("name": not nicknames, not historic),
    and English or unlabelled historic names ("former") only when the feature has
    HISTORIC_MIN_POPULATION people or more and the name's key is in `formers` (curated)."""
    picked = {"abbr": [], "code": [], "short": [], "name": [], "former": []}
    for a in names:
        if not a.name or len(a.name) > _ALTERNATE_MAX or _INVISIBLE.search(a.name):
            continue
        if a.language == "abbr":
            picked["abbr"].append(a.name)
        elif a.language == "iata":
            if codes:
                picked["code"].append(a.name)
        elif a.historic:
            if population >= HISTORIC_MIN_POPULATION and city_key(a.name) in formers:
                picked["former"].append(a.name)
        elif a.language == "en" and a.short:
            picked["short"].append(a.name)
        elif a.language == "en" and not a.colloquial:
            picked["name"].append(a.name)
    return [(name, kind) for kind, found in picked.items() for name in dict.fromkeys(found)]
