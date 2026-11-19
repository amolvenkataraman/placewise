"""US Census Bureau (public domain): the US pack's `states`, `counties`, `places`, `cbsa`, `csa`
and `zcta` layers.

Inputs, all named in src/placewise/sources/uscensus.json:

- cartographic boundary (CB) shapefiles at 1:500k, generalised from TIGER/Line;
- the national gazetteer files (pipe-separated in 2025, tab-separated before), for each place's
  functional status and internal point;
- SUB-EST (Population Estimates, cities and towns), Latin-1 CSV, for incorporated places'
  populations (CDPs have no annual estimate, except Urban Honolulu: Hawaii has no incorporated
  places, so SUB-EST carries it as one);
- the OMB delineation "list 1" (.xlsx), for CBSA/CSA membership of counties. .xlsx is a zip of XML,
  so it is read with the standard library (`read_xlsx_rows`), no spreadsheet dependency.

**Datum.** CB files are NAD83 geographic (EPSG:4269). In the conterminous US, NAD83 and WGS84 (as
realised today) differ by about 1-2 m, far less than the 1:500k generalisation (tens to hundreds of
metres), so the loader reads them with `read_shapefile(accept_nad83=True)`, as WGS84 without
transforming. Any other
datum (NAD27 is off by up to ~100 m) or a projected file is still refused.

Ids: places and counties `census:<GEOID>`; CBSAs, CSAs and ZCTAs carry a type, because their
GEOIDs collide with each other and with county GEOIDs (ZCTA 06085 is in Connecticut, county 06085
is Santa Clara): `census:cbsa:41860`, `census:csa:488`, `census:zcta:94117`. States use
`iso:US-CA`, the id the world pack's admin1 layer gives the same state.
"""

import csv
import logging
import re
import zipfile
from collections import defaultdict
from pathlib import PurePosixPath
from xml.etree import ElementTree

from placewise.io import read_shapefile
from placewise.model import Feature

from ...layer import LayerData

SOURCE = "uscensus"
POPULATION_NULL = -1  # i8 sentinel: no estimate (CDPs, Island Areas)
# LSAD codes of statistical places: census designated place, and Puerto Rico's comunidad and zona urbana
CDP_LSAD = frozenset({"57", "55", "62"})
INCORPORATED_SUMLEV = "162"  # SUB-EST: incorporated place (157 is a place's part in one county)

log = logging.getLogger(__name__)

_CELL_REF = re.compile(r"([A-Z]+)\d*")


# --- reading -----------------------------------------------------------------------------------


def read_census_shapefile(path):
    """read_shapefile, accepting NAD83 longitude/latitude as WGS84 (see the module docstring)."""
    return read_shapefile(path, accept_nad83=True)


def read_gazetteer(path):
    """{GEOID: {column: value}} from a national gazetteer file. Values are stripped: older years pad
    the last column with spaces."""
    with open(path, encoding="utf-8", newline="") as f:
        header = f.readline().rstrip("\r\n")
        sep = "|" if "|" in header else "\t"
        names = [name.strip() for name in header.split(sep)]
        rows = {}
        for number, line in enumerate(f, 2):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            values = [v.strip() for v in line.split(sep)]
            if len(values) != len(names):
                raise ValueError(f"{path}: line {number} has {len(values)} fields, expected {len(names)}")
            row = dict(zip(names, values, strict=True))
            rows[row["GEOID"]] = row
    return rows


def _population_column(header):
    years = [int(m.group(1)) for name in header if (m := re.fullmatch(r"POPESTIMATE(\d{4})", name))]
    if not years:
        raise ValueError("no POPESTIMATE<year> column")
    return max(years)


def population_year(path):
    """The year of the newest estimate in a SUB-EST file (its last POPESTIMATE<year> column)."""
    with open(path, encoding="latin-1", newline="") as f:
        return _population_column(next(csv.reader(f)))


def read_population(path):
    """{place GEOID: newest population estimate} for incorporated places (SUMLEV 162) in SUB-EST.
    The file is Latin-1; only codes and numbers are used from it."""
    with open(path, encoding="latin-1", newline="") as f:
        reader = csv.DictReader(f)
        column = f"POPESTIMATE{_population_column(reader.fieldnames)}"
        return {
            row["STATE"] + row["PLACE"]: int(row[column])
            for row in reader
            if row["SUMLEV"] == INCORPORATED_SUMLEV and row[column].strip()
        }


def read_xlsx_rows(path):
    """The first sheet of an .xlsx as lists of str, one per <row>, each cell at its column (gaps
    are ""). Standard library only: shared strings, inline strings and plain values. Tags are
    matched by local name, so the OOXML namespaces don't matter."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            shared = [_all_text(si) for si in root if _local(si.tag) == "si"]
        sheet = ElementTree.fromstring(z.read(_first_sheet(z)))
    rows = []
    for row in (e for e in sheet.iter() if _local(e.tag) == "row"):
        values = {}
        for position, cell in enumerate(c for c in row if _local(c.tag) == "c"):
            ref = _CELL_REF.match(cell.get("r", ""))
            column = _column_index(ref.group(1)) if ref else position
            kind = cell.get("t")
            if kind == "inlineStr":
                text = _all_text(cell)
            else:
                v = next((e for e in cell if _local(e.tag) == "v"), None)
                text = "" if v is None or v.text is None else v.text
                if kind == "s" and text:
                    text = shared[int(text)]
            if text != "":
                values[column] = text
        rows.append([values.get(c, "") for c in range(max(values) + 1)] if values else [])
    return rows


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _all_text(element):
    """The text of every <t> under an element (rich text splits a string into runs)."""
    return "".join(e.text or "" for e in element.iter() if _local(e.tag) == "t")


def _first_sheet(z):
    workbook = ElementTree.fromstring(z.read("xl/workbook.xml"))
    first = next(e for e in workbook.iter() if _local(e.tag) == "sheet")
    rel_id = next(v for k, v in first.attrib.items() if _local(k) == "id")
    rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rel_id)
    return target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)


def _column_index(letters):
    index = 0
    for ch in letters:
        index = index * 26 + ord(ch) - ord("A") + 1
    return index - 1


def read_delineation(path):
    """One dict per county row of the OMB delineation list 1: cbsa, csa, metdiv codes, type
    ("metro" | "micro"), county (5-digit FIPS) and central (bool). Title rows above the header
    ("CBSA Code", ...) and footnotes below the data are skipped."""
    rows = read_xlsx_rows(path)
    start = next((i for i, row in enumerate(rows) if row and row[0].strip() == "CBSA Code"), None)
    if start is None:
        raise ValueError(f"{path}: no 'CBSA Code' header row")
    header = {name.strip(): i for i, name in enumerate(rows[start])}

    def get(row, name):
        i = header[name]
        return row[i].strip() if i < len(row) else ""

    out = []
    for row in rows[start + 1 :]:
        if not row or not re.fullmatch(r"\d{5}", row[0].strip()):
            continue  # blank spacer or footnote
        kind = get(row, "Metropolitan/Micropolitan Statistical Area")
        out.append(
            {
                "cbsa": get(row, "CBSA Code"),
                "csa": get(row, "CSA Code"),
                "metdiv": get(row, "Metropolitan Division Code"),
                "type": "metro" if kind.startswith("Metropolitan") else "micro",
                "county": get(row, "FIPS State Code").zfill(2) + get(row, "FIPS County Code").zfill(3),
                "central": get(row, "Central/Outlying County") == "Central",
            }
        )
    return out


# --- layers ------------------------------------------------------------------------------------


def states(shp_path):
    """States, DC, Puerto Rico and the Island Areas; id "iso:US-<USPS>", sorted by FIPS code."""
    raw = _sorted(read_census_shapefile(shp_path), lambda p: _text(p["GEOID"]))
    props = [f.properties for f in raw]
    ids = [f"iso:US-{_text(p['STUSPS'])}" for p in props]
    columns = {
        "id": ids,
        "name": [_text(p["NAME"]) for p in props],
        "usps": [_text(p["STUSPS"]) for p in props],
        "statefp": [_text(p["STATEFP"]) for p in props],
    }
    return _polygons("states", raw, ids, columns)


def counties(shp_path, delineation=()):
    """Counties and equivalents; name with its LSAD ("San Francisco County"), CBSA/CSA codes and
    central/outlying from the delineation ("" for counties outside any CBSA)."""
    raw = _sorted(read_census_shapefile(shp_path), lambda p: _text(p["GEOID"]))
    props = [f.properties for f in raw]
    by_county = {row["county"]: row for row in delineation}
    geoids = [_text(p["GEOID"]) for p in props]
    member = [by_county.get(g, {}) for g in geoids]
    if delineation and (missing := sorted(set(by_county) - set(geoids))):
        log.warning("delineation counties not in the county file: %s", ", ".join(missing))
    ids = [f"census:{g}" for g in geoids]
    columns = {
        "id": ids,
        "name": [_text(p["NAMELSAD"]) for p in props],
        "basename": [_text(p["NAME"]) for p in props],
        "lsad": [_lsad(p) for p in props],
        "state": [_text(p["STUSPS"]) for p in props],
        "statefp": [_text(p["STATEFP"]) for p in props],
        "countyfp": [_text(p["COUNTYFP"]) for p in props],
        "cbsa": [m.get("cbsa", "") for m in member],
        "csa": [m.get("csa", "") for m in member],
        "central": [("central" if m["central"] else "outlying") if m else "" for m in member],
    }
    return _polygons("counties", raw, ids, columns)


def places(shp_path, gazetteer=None, population=None):
    """Incorporated places and CDPs. Incorporated places come first, so they win the rare point a
    CDP also covers; within each group, by GEOID. `gazetteer` ({GEOID: row}) gives FUNCSTAT and
    the internal point, `population` ({GEOID: int}) the estimate; places missing from either (the
    Island Areas are in neither; CDPs other than Urban Honolulu have no estimate, nor do inactive
    places) get nulls. The internal point is the gazetteer's, computed from full TIGER/Line
    shapes: it can fall outside the shoreline-clipped CB polygon (San Francisco's is on the
    Farallon Islands, outside the 1:500k shape)."""
    gazetteer, population = gazetteer or {}, population or {}

    def order(p):
        return (_text(p["LSAD"]) in CDP_LSAD, _text(p["GEOID"]))

    raw = _sorted(read_census_shapefile(shp_path), order)
    props = [f.properties for f in raw]
    geoids = [_text(p["GEOID"]) for p in props]
    gaz = [gazetteer.get(g, {}) for g in geoids]
    ids = [f"census:{g}" for g in geoids]
    columns = {
        "id": ids,
        "name": [_text(p["NAME"]) for p in props],
        "full_name": [_text(p["NAMELSAD"]) for p in props],
        "lsad": [_lsad(p) for p in props],
        "lsad_code": [_text(p["LSAD"]) for p in props],
        "class": ["cdp" if _text(p["LSAD"]) in CDP_LSAD else "incorporated" for p in props],
        "funcstat": [g.get("FUNCSTAT", "") for g in gaz],
        "state": [_text(p["STUSPS"]) for p in props],
        "statefp": [_text(p["STATEFP"]) for p in props],
        "population": [population.get(g) for g in geoids],
        "aland": [int(p.get("ALAND") or 0) for p in props],
        "intpt_lat": [_float(g.get("INTPTLAT")) for g in gaz],
        "intpt_lon": [_float(g.get("INTPTLONG")) for g in gaz],
    }
    if gazetteer:
        log.info("places: %d of %d in the gazetteer", sum(bool(g) for g in gaz), len(gaz))
    if population:
        log.info("places: %d with a population estimate", sum(g in population for g in geoids))
    return _polygons("places", raw, ids, columns, population="i8", aland="i8", intpt_lat="f8", intpt_lon="f8")


def cbsa(shp_path, delineation=()):
    """Metropolitan and micropolitan statistical areas: name with its type ("... Metro Area"),
    the CSA it belongs to and its member counties (comma-separated FIPS codes)."""
    raw = _sorted(read_census_shapefile(shp_path), lambda p: _text(p["GEOID"]))
    props = [f.properties for f in raw]
    members = defaultdict(set)
    for row in delineation:
        members[row["cbsa"]].add(row["county"])
    codes = [_text(p["GEOID"]) for p in props]
    ids = [f"census:cbsa:{c}" for c in codes]
    columns = {
        "id": ids,
        "name": [_text(p["NAMELSAD"]) for p in props],
        "title": [_text(p["NAME"]) for p in props],
        "code": codes,
        "type": [{"M1": "metro", "M2": "micro"}.get(_text(p["LSAD"]), "") for p in props],
        "csa": [_text(p.get("CSAFP")) for p in props],
        "counties": [",".join(sorted(members[c])) for c in codes],
    }
    return _polygons("cbsa", raw, ids, columns)


def csa(shp_path, delineation=()):
    """Combined statistical areas ("San Jose-San Francisco-Oakland, CA CSA"), with member CBSAs
    and counties from the delineation."""
    raw = _sorted(read_census_shapefile(shp_path), lambda p: _text(p["GEOID"]))
    props = [f.properties for f in raw]
    cbsas, counties_ = defaultdict(set), defaultdict(set)
    for row in delineation:
        if row["csa"]:
            cbsas[row["csa"]].add(row["cbsa"])
            counties_[row["csa"]].add(row["county"])
    codes = [_text(p["GEOID"]) for p in props]
    ids = [f"census:csa:{c}" for c in codes]
    columns = {
        "id": ids,
        "name": [_text(p["NAMELSAD"]) for p in props],
        "title": [_text(p["NAME"]) for p in props],
        "code": codes,
        "cbsas": [",".join(sorted(cbsas[c])) for c in codes],
        "counties": [",".join(sorted(counties_[c])) for c in codes],
    }
    return _polygons("csa", raw, ids, columns)


def _zcta_columns(codes, gazetteer, aland):
    gaz = [gazetteer.get(c, {}) for c in codes]
    return {
        "id": [f"census:zcta:{c}" for c in codes],
        "name": list(codes),
        "aland": aland,
        "intpt_lat": [_float(g.get("INTPTLAT")) for g in gaz],
        "intpt_lon": [_float(g.get("INTPTLONG")) for g in gaz],
    }


def zcta(shp_path, gazetteer=None):
    """ZIP Code Tabulation Areas as polygons. ZCTAs are the Census Bureau's areal approximation of
    USPS ZIP Codes (which are delivery routes, not areas, and are not published as such): most
    addresses' ZIP Code matches their ZCTA, but not all, and PO-box-only ZIP Codes have no ZCTA."""
    raw = _sorted(read_census_shapefile(shp_path), lambda p: _text(p["ZCTA5CE20"]))
    codes = [_text(f.properties["ZCTA5CE20"]) for f in raw]
    columns = _zcta_columns(codes, gazetteer or {}, [int(f.properties.get("ALAND20") or 0) for f in raw])
    return _polygons("zcta", raw, columns["id"], columns, aland="i8", intpt_lat="f8", intpt_lon="f8")


def zcta_points(gazetteer):
    """ZCTAs as points at the gazetteer's internal point (the smaller alternative to `zcta`)."""
    codes = sorted(gazetteer)
    columns = _zcta_columns(codes, gazetteer, [int(gazetteer[c]["ALAND"]) for c in codes])
    lat, lon = columns.pop("intpt_lat"), columns.pop("intpt_lon")
    types = {name: "str" for name in columns}
    types["aland"] = "i8"
    return LayerData("zcta", "point", columns, (SOURCE,), lat=lat, lon=lon, types=types)


# --- helpers -----------------------------------------------------------------------------------


def _polygons(name, raw, ids, columns, **numeric):
    types = {column: numeric.get(column, "str") for column in columns}
    nulls = {"population": POPULATION_NULL} if "population" in columns else {}
    features = [Feature(f.outlines, {}, fid) for f, fid in zip(raw, ids, strict=True)]
    return LayerData(name, "polygon", columns, (SOURCE,), features=features, types=types, nulls=nulls)


def _sorted(features, key):
    return sorted(features, key=lambda f: key(f.properties))


def _lsad(p):
    """The LSAD as words ("city", "CDP", "County"): NAMELSAD less NAME."""
    name, full = _text(p["NAME"]), _text(p["NAMELSAD"])
    return full[len(name) :].strip() if full.startswith(name) else ""


def _text(value):
    return "" if value is None else str(value).strip()


def _float(value):
    return float(value) if value not in (None, "") else float("nan")
