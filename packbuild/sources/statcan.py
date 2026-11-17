"""Statistics Canada, 2021 Census (Statistics Canada Open Licence): the Canada pack's polygon layers.

Boundaries come from the 2021 cartographic boundary files (clipped to the shoreline) for
provinces/territories, census divisions, census subdivisions and CMAs/CAs, and from the 2021
Census Forward Sortation Area boundary file. They are published only in Statistics Canada Lambert
(EPSG:3347), so rings are simplified in metres and unprojected here (see packbuild.projection).
Either input works: the shapefiles inside StatCan's zips, or a folder of ArcGIS REST query pages
(Esri JSON, outSR 3347) from StatCan's map service of the same files (packbuild.arcgis).

Populations come from the census "Population and dwelling counts" tables (98-10-0002-01 for
Canada, provinces, CDs and CSDs; 98-10-0005-01 for CMAs/CAs; 98-10-0019-01 for FSAs), joined on
the Dissemination Geography Unique Identifier (DGUID). A suppressed count ("..", e.g. incompletely
enumerated reserves) is null, not zero.

Ids are "statcan:<UID>": PRUID (2 digits), CDUID (4), CSDUID (7), CMAPUID (5: province + CMA, so
both parts of a CMA that crosses a provincial border have their own feature) and CFSAUID ("M5V").
"""

import csv
import json
import logging
import re
from pathlib import Path

import numpy as np

from placewise.io.shapefile import _encoding, _read_dbf, _read_shp  # low-level parsers, no CRS check

from ..layer import LayerData
from ..polygons import to_feature
from ..projection import STATCAN_LAMBERT

BOUNDARIES = "statcan-boundaries-2021"
FSA = "statcan-fsa-2021"
POPULATION = "statcan-population-2021"

# Standard Geographical Classification 2021: PRUID -> the two-letter province/territory code
PROVINCE_CODES = {
    "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON", "46": "MB",
    "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU",
}  # fmt: skip

# Douglas-Peucker tolerance in metres. The cartographic files have a vertex every few metres;
# 10 m is below what a phone's GPS can tell apart and cuts the vertex count several times.
DEFAULT_TOLERANCE_M = 10.0
POPULATION_NULL = -1

# DGUID = vintage + type + schema + UID (Dictionary, Census of Population 2021, "DGUID")
_DGUID_SCHEMA = {
    "pr": "2021A0002",
    "cd": "2021A0003",
    "csd": "2021A0005",
    "fsa": "2021A0011",
    "cma": "2021S0503",  # census metropolitan area
    "ca": "2021S0504",  # census agglomeration
}
_POPULATION_HEADER = re.compile(r"Population, 2021\s*\[1\]")
_PART = re.compile(
    r"\s*\([^()]*\bpart(ie)?\b[^()]*\)\s*$", re.IGNORECASE
)  # "(Ontario part / partie de l'Ontario)"
_PRJ_PARAMETERS = {  # .prj name -> attribute of STATCAN_LAMBERT
    "False_Easting": "false_easting",
    "False_Northing": "false_northing",
    "Central_Meridian": "lon_origin",
    "Standard_Parallel_1": "lat_1",
    "Standard_Parallel_2": "lat_2",
    "Latitude_Of_Origin": "lat_origin",
}
_SERVICE_WKIDS = {3347}

log = logging.getLogger(__name__)


# --- population ---------------------------------------------------------------------------------


def dguid(level, uid):
    """The 2021 DGUID of a geographic area: level is pr, cd, csd, fsa, cma or ca."""
    return _DGUID_SCHEMA[level] + uid


def read_population(*paths):
    """{DGUID: 2021 population or None} from one or more census population tables (CSV)."""
    out = {}
    for path in paths:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = csv.reader(f)
            header = next(rows)
            try:
                guid = header.index("DGUID")
                col = next(i for i, h in enumerate(header) if _POPULATION_HEADER.search(h))
            except (ValueError, StopIteration):
                raise ValueError(f"{path}: no DGUID or 'Population, 2021 [1]' column") from None
            for row in rows:
                if len(row) <= col:  # the blank lines at the end of the file
                    continue
                value = row[col].strip()
                out[row[guid]] = int(value) if value else None
    return out


# --- boundaries ---------------------------------------------------------------------------------


def read_boundaries(path):
    """(attributes, rings) per record, rings as (n, 2) EPSG:3347 arrays. `path` is a .shp file,
    or a folder of ArcGIS REST query pages (page-*.json)."""
    path = Path(path)
    if path.is_dir():
        return _read_service_pages(path)
    return _read_lambert_shapefile(path)


def _read_lambert_shapefile(path):
    shp = path.with_suffix(".shp")
    _check_prj(shp.with_suffix(".prj"))
    records = _read_dbf(shp.with_suffix(".dbf"), _encoding(shp.with_suffix(".cpg")))
    for rings, props in zip(_read_shp(shp), records, strict=True):
        if rings is None:
            log.warning("%s: record %s has no shape; skipped", shp.name, props)
            continue
        yield props, rings


def _check_prj(prj):
    if not prj.exists():
        raise ValueError(f"{prj.name}: missing .prj; StatCan boundary files are in EPSG:3347 and say so")
    text = prj.read_text(encoding="utf-8", errors="replace")
    if "LAMBERT_CONFORMAL_CONIC" not in text.upper():
        raise ValueError(f"{prj.name}: not Lambert conformal conic (EPSG:3347, Statistics Canada Lambert)")
    if "GRS_1980" not in text.upper() and "GRS 1980" not in text.upper():
        raise ValueError(f"{prj.name}: not on the GRS 1980 ellipsoid (NAD83)")
    params = {k.lower(): float(v) for k, v in re.findall(r'PARAMETER\["([^"]+)",\s*([-+0-9.eE]+)\]', text)}
    for name, attr in _PRJ_PARAMETERS.items():
        want = getattr(STATCAN_LAMBERT, attr)
        got = params.get(name.lower())
        if got is None or abs(got - want) > 1e-5:
            raise ValueError(f"{prj.name}: {name} is {got}, expected {want} (EPSG:3347)")


def _read_service_pages(folder):
    pages = sorted(folder.glob("page-*.json"))
    if not pages:
        raise ValueError(f"{folder}: no page-*.json files")
    for page in pages:
        data = json.loads(page.read_text(encoding="utf-8"))
        if "error" in data:
            raise ValueError(f"{page}: the service returned an error: {data['error']}")
        sr = data.get("spatialReference", {})
        if not ({sr.get("wkid"), sr.get("latestWkid")} & _SERVICE_WKIDS):
            raise ValueError(f"{page}: spatial reference {sr} is not EPSG:3347")
        for feature in data.get("features", []):
            rings = (feature.get("geometry") or {}).get("rings")
            if not rings:
                log.warning("%s: feature %s has no shape; skipped", page.name, feature.get("attributes"))
                continue
            yield feature["attributes"], [np.asarray(r, dtype=np.float64)[:, :2] for r in rings]


# --- layers -------------------------------------------------------------------------------------


def provinces(path, population=None, tolerance_m=DEFAULT_TOLERANCE_M):
    """Provinces and territories: id statcan:<PRUID>, English and French names, SGC code."""

    def row(p):
        pruid = _text(p["PRUID"])
        return {
            "id": f"statcan:{pruid}",
            "name": _text(p["PRENAME"]),
            "name_fr": _text(p["PRFNAME"]),
            "code": _province(pruid),
            "pruid": pruid,
            "population": _population(population, dguid("pr", pruid)),
        }

    return _layer("provinces", path, row, (BOUNDARIES,), population, tolerance_m)


def census_divisions(path, population=None, tolerance_m=DEFAULT_TOLERANCE_M):
    """Census divisions (counties, regional municipalities such as Halton and Peel, ...)."""

    def row(p):
        cduid = _text(p["CDUID"])
        return {
            "id": f"statcan:{cduid}",
            "name": _text(p["CDNAME"]),
            "cdtype": _text(p["CDTYPE"]),
            "province": _province(_text(p["PRUID"])),
            "population": _population(population, dguid("cd", cduid)),
        }

    return _layer("cd", path, row, (BOUNDARIES,), population, tolerance_m)


def census_subdivisions(path, population=None, tolerance_m=DEFAULT_TOLERANCE_M):
    """Census subdivisions: municipalities (and their equivalents: reserves, unorganised areas).
    cduid is the CSDUID's first four digits, as the Standard Geographical Classification nests."""

    def row(p):
        csduid = _text(p["CSDUID"])
        return {
            "id": f"statcan:{csduid}",
            "name": _text(p["CSDNAME"]),
            "csdtype": _text(p["CSDTYPE"]),
            "province": _province(_text(p["PRUID"])),
            "cduid": csduid[:4],
            "population": _population(population, dguid("csd", csduid)),
        }

    return _layer("csd", path, row, (BOUNDARIES,), population, tolerance_m)


def metro_areas(path, population=None, tolerance_m=DEFAULT_TOLERANCE_M):
    """Census metropolitan areas (CMATYPE B) and census agglomerations (D tracted, K not). One
    feature per provincial part; name drops the "(Ontario part / ...)" suffix (kept in name_full)
    and population is the whole CMA's, the same on both parts."""

    def row(p):
        cmauid, cmatype = _text(p["CMAUID"]), _text(p["CMATYPE"])
        full = _text(p["CMANAME"])
        kind = "CMA" if cmatype == "B" else "CA"
        return {
            "id": f"statcan:{_text(p['CMAPUID'])}",
            "name": _PART.sub("", full),
            "name_full": full,
            "cmauid": cmauid,
            "cmatype": cmatype,
            "kind": kind,
            "province": _province(_text(p["PRUID"])),
            "population": _population(population, dguid(kind.lower(), cmauid)),
        }

    return _layer("cma", path, row, (BOUNDARIES,), population, tolerance_m)


def forward_sortation_areas(path, population=None, tolerance_m=DEFAULT_TOLERANCE_M):
    """Census forward sortation areas: the first three characters of postal codes, as census
    respondents reported them (each dissemination area gets one FSA), not Canada Post's own."""

    def row(p):
        fsa = _text(p["CFSAUID"])
        return {
            "id": f"statcan:{fsa}",
            "name": fsa,
            "province": _province(_text(p["PRUID"])),
            "population": _population(population, dguid("fsa", fsa)),
        }

    return _layer("fsa", path, row, (FSA,), population, tolerance_m)


def _layer(name, path, row, sources, population, tolerance_m):
    columns, features = {}, []
    for props, rings in read_boundaries(path):
        values = row(props)
        for key, value in values.items():
            columns.setdefault(key, []).append(value)
        features.append(to_feature(rings, tolerance_m, STATCAN_LAMBERT, values["id"]))
    if population is not None:
        missing = sum(v is None for v in columns.get("population", ()))
        if missing:
            log.info("%s: %d of %d features have no 2021 population", name, missing, len(features))
        sources = (*sources, POPULATION)
    types = {key: "str" for key in columns}
    types["population"] = "i8"
    return LayerData(
        name,
        "polygon",
        columns,
        sources,
        features=features,
        types=types,
        nulls={"population": POPULATION_NULL},
    )


# layer -> the attribute its ids are made of
UID_FIELDS = {"provinces": "PRUID", "cd": "CDUID", "csd": "CSDUID", "cma": "CMAPUID", "fsa": "CFSAUID"}


def raw_rings(paths, ids):
    """{id: rings} for the wanted ids ("statcan:3520"), read again from the boundary files of the
    layers in `paths` ({layer: path}) and left unsimplified and projected (EPSG:3347): neighbours'
    shared borders still have the same vertices, so a union of them can drop those borders."""
    wanted, out = set(ids), {}
    for layer, path in paths.items():
        field = UID_FIELDS[layer]
        for props, rings in read_boundaries(path):
            fid = f"statcan:{_text(props[field])}"
            if fid in wanted:
                out.setdefault(fid, []).extend(rings)
    return out


def _population(table, key):
    return None if table is None else table.get(key)


def _province(pruid):
    try:
        return PROVINCE_CODES[pruid]
    except KeyError:
        raise ValueError(f"unknown province/territory PRUID {pruid!r}") from None


def _text(value):
    """Clean text: StatCan pads some names with double spaces ("Division No.  1"); fold them."""
    return "" if value is None else " ".join(str(value).replace("\x00", " ").split())
