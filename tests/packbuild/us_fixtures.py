# ruff: noqa: E501  (rows copied from the real files are longer than a line)
"""Tiny US Census-like inputs for the US pack tests, written into a temporary directory.

Attribute names follow the 2025 cartographic boundary files (and cb_2020_us_zcta520), the 2025
gazetteer, SUB-EST2025 and the July 2023 delineation file (list1_2023.xlsx). Shapes are coarse
boxes around real places, not real borders; the values in the text files are copied from the real
files, with a few deliberate extras so each rule has a row to exercise.
"""

import itertools
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import shapefile  # pyshp

# exactly what the Census files ship
NAD83_PRJ = (
    'GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137,'
    '298.257222101]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)
WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
NAD27_PRJ = (
    'GEOGCS["GCS_North_American_1927",DATUM["D_North_American_1927",SPHEROID["Clarke_1866",6378206.4,'
    '294.9786982]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)
NAD83_ALBERS_PRJ = (
    'PROJCS["NAD_1983_Albers",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
    'SPHEROID["GRS_1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Albers"],UNIT["Meter",1]]'
)

C = ("C", 100)
N = ("N", 14, 0)


def box(south, west, north, east):
    """One clockwise ring in (lon, lat), as the shapefile spec wants outer rings."""
    return [[(west, south), (west, north), (east, north), (east, south), (west, south)]]


def write_shapefile(base, fields, rows, prj=NAD83_PRJ):
    base = Path(base)
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        for field in fields:
            w.field(*field)
        for rings, record in rows:
            w.poly(rings)
            w.record(*record)
    if prj is not None:
        base.with_suffix(".prj").write_text(prj)
    base.with_suffix(".cpg").write_text("UTF-8")
    return base.with_suffix(".shp")


# California with its diagonal eastern border (Lake Tahoe to the Colorado River), Nevada beside it
CA_RING = [(-124.5, 32.5), (-124.5, 42.0), (-120.0, 42.0), (-120.0, 39.0), (-114.6, 35.0), (-114.6, 32.5)]
NV_RING = [(-120.0, 39.0), (-120.0, 42.0), (-114.0, 42.0), (-114.0, 35.0), (-114.6, 35.0)]


def _clockwise(ring):
    ring = [*ring, ring[0]]
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in itertools.pairwise(ring))
    return ring if area < 0 else ring[::-1]


def states(folder):
    fields = [("STATEFP", *C), ("STATENS", *C), ("GEOIDFQ", *C), ("GEOID", *C), ("STUSPS", *C),
              ("NAME", *C), ("LSAD", *C), ("ALAND", *N), ("AWATER", *N)]  # fmt: skip
    rows = [
        ([_clockwise(NV_RING)], ("32", "01779793", "0400000US32", "32", "NV", "Nevada", "00", 284537074263, 1839852286)),
        ([_clockwise(CA_RING)], ("06", "01779778", "0400000US06", "06", "CA", "California", "00", 403673617862, 20291712025)),
        (box(13.2, 144.6, 13.7, 145.0), ("66", "01802705", "0400000US66", "66", "GU", "Guam", "00", 543555849, 934337453)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2025_us_state_500k", fields, rows)


def counties(folder):
    fields = [("STATEFP", *C), ("COUNTYFP", *C), ("COUNTYNS", *C), ("GEOIDFQ", *C), ("GEOID", *C), ("NAME", *C),
              ("NAMELSAD", *C), ("STUSPS", *C), ("STATE_NAME", *C), ("LSAD", *C), ("ALAND", *N), ("AWATER", *N)]  # fmt: skip
    rows = [
        (box(35.0, -115.9, 36.85, -114.0), ("32", "003", "00863278", "0500000US32003", "32003", "Clark",
         "Clark County", "NV", "Nevada", "06", 20438970461, 438478013)),
        (box(37.70, -122.52, 37.83, -122.35), ("06", "075", "00277302", "0500000US06075", "06075",
         "San Francisco", "San Francisco County", "CA", "California", "06", 121485107, 479107241)),
        (box(37.45, -122.35, 37.91, -121.47), ("06", "001", "01675839", "0500000US06001", "06001", "Alameda",
         "Alameda County", "CA", "California", "06", 1909616630, 216916717)),
        (box(39.0, -120.0, 42.0, -119.0), ("32", "031", "00863283", "0500000US32031", "32031", "Washoe",
         "Washoe County", "NV", "Nevada", "06", 16304020829, 438945658)),
        (box(37.2, -120.4, 37.9, -119.3), ("06", "043", "00277286", "0500000US06043", "06043", "Mariposa",
         "Mariposa County", "CA", "California", "06", 3752472156, 36225644)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2025_us_county_500k", fields, rows)


def places(folder):
    fields = [("STATEFP", *C), ("PLACEFP", *C), ("PLACENS", *C), ("GEOIDFQ", *C), ("GEOID", *C), ("NAME", *C),
              ("NAMELSAD", *C), ("STUSPS", *C), ("STATE_NAME", *C), ("LSAD", *C), ("ALAND", *N), ("AWATER", *N)]  # fmt: skip
    rows = [
        # the CDP first in the file: the layer puts incorporated places before CDPs
        (box(36.05, -115.25, 36.13, -115.05), ("32", "54600", "02409023", "1600000US3254600", "3254600",
         "Paradise", "Paradise CDP", "NV", "Nevada", "57", 109826233, 0)),
        (box(37.70, -122.52, 37.83, -122.35), ("06", "67000", "02411786", "1600000US0667000", "0667000",
         "San Francisco", "San Francisco city", "CA", "California", "25", 120913550, 479701988)),
        (box(37.70, -122.35, 37.89, -122.11), ("06", "53000", "02411292", "1600000US0653000", "0653000",
         "Oakland", "Oakland city", "CA", "California", "25", 144943635, 57160794)),
        (box(36.13, -115.35, 36.38, -115.06), ("32", "40000", "02411630", "1600000US3240000", "3240000",
         "Las Vegas", "Las Vegas city", "NV", "Nevada", "25", 367428873, 138524)),
        (box(39.43, -119.95, 39.65, -119.70), ("32", "60600", "02410923", "1600000US3260600", "3260600",
         "Reno", "Reno city", "NV", "Nevada", "25", 283081084, 7331473)),
        # an Island Area place: in the boundary file but not in the gazetteer or SUB-EST
        (box(13.46, 144.74, 13.48, 144.76), ("66", "33400", "02407977", "1600000US6633400", "6633400",
         "Hagåtña", "Hagåtña village", "GU", "Guam", "47", 2580000, 0)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2025_us_place_500k", fields, rows)


def cbsa(folder):
    fields = [("CSAFP", *C), ("CBSAFP", *C), ("GEOIDFQ", *C), ("GEOID", *C), ("NAME", *C), ("NAMELSAD", *C),
              ("LSAD", *C), ("ALAND", *N), ("AWATER", *N)]  # fmt: skip
    rows = [
        (box(37.45, -122.52, 37.91, -121.47), ("488", "41860", "310M700US41860", "41860",
         "San Francisco-Oakland-Fremont, CA", "San Francisco-Oakland-Fremont, CA Metro Area", "M1",
         6398000000, 2600000000)),
        (box(35.0, -115.9, 36.85, -114.0), ("332", "29820", "310M700US29820", "29820",
         "Las Vegas-Henderson-North Las Vegas, NV", "Las Vegas-Henderson-North Las Vegas, NV Metro Area", "M1",
         20438970461, 438478013)),
        (box(39.0, -120.0, 42.0, -119.0), ("456", "39900", "310M700US39900", "39900", "Reno, NV",
         "Reno, NV Metro Area", "M1", 17000000000, 500000000)),
        (box(40.0, -117.0, 42.0, -114.0), ("", "21220", "310M700US21220", "21220", "Elko, NV",
         "Elko, NV Micro Area", "M2", 45000000000, 100000000)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2025_us_cbsa_500k", fields, rows)


def csa(folder):
    fields = [("CSAFP", *C), ("GEOIDFQ", *C), ("GEOID", *C), ("NAME", *C), ("NAMELSAD", *C), ("LSAD", *C),
              ("ALAND", *N), ("AWATER", *N)]  # fmt: skip
    rows = [
        (box(36.9, -123.0, 38.9, -121.2), ("488", "330M700US488", "488", "San Jose-San Francisco-Oakland, CA",
         "San Jose-San Francisco-Oakland, CA CSA", "M0", 31000000000, 3200000000)),
        (box(35.0, -116.5, 37.0, -114.0), ("332", "330M700US332", "332", "Las Vegas-Henderson, NV",
         "Las Vegas-Henderson, NV CSA", "M0", 49000000000, 500000000)),
        (box(38.5, -120.5, 42.0, -119.0), ("456", "330M700US456", "456",
         "Reno-Carson City-Gardnerville Ranchos, NV-CA", "Reno-Carson City-Gardnerville Ranchos, NV-CA CSA",
         "M0", 25000000000, 900000000)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2025_us_csa_500k", fields, rows)


def zcta(folder):
    fields = [("ZCTA5CE20", *C), ("AFFGEOID20", *C), ("GEOID20", *C), ("NAME20", *C), ("LSAD20", *C),
              ("ALAND20", *N), ("AWATER20", *N)]  # fmt: skip
    rows = [
        (box(37.76, -122.52, 37.78, -122.44), ("94117", "860Z200US94117", "94117", "94117", "Z5", 3301059, 0)),
        (box(36.10, -115.19, 36.14, -115.15), ("89109", "860Z200US89109", "89109", "89109", "Z5", 10683404, 0)),
        (box(37.60, -119.90, 37.95, -119.20), ("95389", "860Z200US95389", "95389", "95389", "Z5", 778855970, 5193335)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2020_us_zcta520_500k", fields, rows)


# 2025_Gaz_place_national.txt: pipe-separated in 2025 (tab-separated in earlier years); real
# rows, with the trailing spaces older gazetteers pad the last column with
GAZ_PLACE = """\
USPS|GEOID|GEOIDFQ|ANSICODE|NAME|LSAD|FUNCSTAT|ALAND|AWATER|ALAND_SQMI|AWATER_SQMI|INTPTLAT|INTPTLONG
CA|0653000|1600000US0653000|02411292|Oakland city|25|A|144943635|57160794|55.963|22.07|37.769846|-122.22569
CA|0667000|1600000US0667000|02411786|San Francisco city|25|A|120913550|479701988|46.685|185.214|37.727239|-123.032229
NV|3240000|1600000US3240000|02411630|Las Vegas city|25|A|367428873|138524|141.865|0.053|36.233499|-115.264037   \n\
NV|3254600|1600000US3254600|02409023|Paradise CDP|57|S|109826233|0|42.404|0.|36.087148|-115.135519
NV|3260600|1600000US3260600|02410923|Reno city|25|A|283081084|7331473|109.298|2.831|39.549097|-119.849907
"""

GAZ_ZCTA = """\
GEOID|GEOIDFQ|ALAND|AWATER|ALAND_SQMI|AWATER_SQMI|INTPTLAT|INTPTLONG
89109|860Z200US89109|10683404|0|4.125|0.|36.131622|-115.169932
94117|860Z200US94117|3301059|0|1.275|0.|37.770051|-122.44428
95389|860Z200US95389|778855970|5193335|300.718|2.005|37.784127|-119.428263
"""

# sub-est2025.csv is Latin-1 (Española); only SUMLEV 162 (incorporated place) rows count
SUB_EST = (
    "SUMLEV,STATE,COUNTY,PLACE,COUSUB,CONCIT,PRIMGEO_FLAG,FUNCSTAT,NAME,STNAME,ESTIMATESBASE2020,"
    "POPESTIMATE2020,POPESTIMATE2021,POPESTIMATE2022,POPESTIMATE2023,POPESTIMATE2024,POPESTIMATE2025\n"
    "040,06,000,00000,00000,00000,0,A,California,California,39538245,39501653,39142991,39029342,"
    "38965193,39431263,39529101\n"
    "050,06,075,00000,00000,00000,0,C,San Francisco County,California,878550,875139,816169,813266,"
    "816926,820945,826079\n"
    "162,06,000,53000,00000,00000,0,A,Oakland city,California,440842,441157,437373,436240,438301,440173,440838\n"
    "162,06,000,67000,00000,00000,0,A,San Francisco city,California,878550,875139,816169,813266,816926,"
    "820945,826079\n"
    "157,06,075,67000,00000,00000,1,A,San Francisco city,California,1,1,1,1,1,1,1\n"
    "162,32,000,40000,00000,00000,0,A,Las Vegas city,Nevada,645774,647676,651865,657003,665642,675152,679817\n"
    "162,32,000,60600,00000,00000,0,A,Reno city,Nevada,264151,265001,270124,273277,275768,280646,283621\n"
    "061,32,031,92000,00000,00000,0,S,Reno CCD,Nevada,9,9,9,9,9,9,9\n"
    "162,35,000,25170,00000,00000,0,A,Espa\xf1ola city,New Mexico,10530,10514,10501,10440,10451,10472,10458\n"
)

# list1_2023.xlsx: a title row, a blank spacer, the header on row 3, data, then footnotes
DELINEATION_HEADER = (
    "CBSA Code", "Metropolitan Division Code", "CSA Code", "CBSA Title",
    "Metropolitan/Micropolitan Statistical Area", "Metropolitan Division Title", "CSA Title",
    "County/County Equivalent", "State Name", "FIPS State Code", "FIPS County Code", "Central/Outlying County",
)  # fmt: skip
DELINEATION_ROWS = [
    ("21220", "", "", "Elko, NV", "Micropolitan Statistical Area", "", "", "Elko County", "Nevada", "32", "007",
     "Central"),
    ("29820", "", "332", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "",
     "Las Vegas-Henderson, NV", "Clark County", "Nevada", "32", "003", "Central"),
    ("39900", "", "456", "Reno, NV", "Metropolitan Statistical Area", "",
     "Reno-Carson City-Gardnerville Ranchos, NV-CA", "Storey County", "Nevada", "32", "029", "Outlying"),
    ("39900", "", "456", "Reno, NV", "Metropolitan Statistical Area", "",
     "Reno-Carson City-Gardnerville Ranchos, NV-CA", "Washoe County", "Nevada", "32", "031", "Central"),
    ("41860", "36084", "488", "San Francisco-Oakland-Fremont, CA", "Metropolitan Statistical Area",
     "Oakland-Fremont-Berkeley, CA", "San Jose-San Francisco-Oakland, CA", "Alameda County", "California",
     "06", "001", "Central"),
    ("41860", "41884", "488", "San Francisco-Oakland-Fremont, CA", "Metropolitan Statistical Area",
     "San Francisco-San Mateo-Redwood City, CA", "San Jose-San Francisco-Oakland, CA", "San Francisco County",
     "California", "06", "075", "Central"),
    ("41940", "", "488", "San Jose-Sunnyvale-Santa Clara, CA", "Metropolitan Statistical Area", "",
     "San Jose-San Francisco-Oakland, CA", "Santa Clara County", "California", "06", "085", "Central"),
]  # fmt: skip
DELINEATION_FOOTNOTES = [
    "Note: The 2023 delineations reflect the 2020 Standards for Delineating Core Based Statistical Areas.",
    "Source: File prepared by U.S. Census Bureau, Population Division, based on OMB Bulletin No. 23-01.",
]


def write_xlsx(path, rows):
    """A minimal .xlsx (one sheet, shared strings), laid out the way Excel writes list1: cell
    references on every cell, empty cells omitted, all codes stored as text."""
    strings, index = [], {}

    def ref(r, c):
        return f"{chr(ord('A') + c)}{r}"

    body = []
    for r, row in enumerate(rows, 1):
        cells = []
        for c, value in enumerate(row):
            if value == "" or value is None:
                continue
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref(r, c)}"><v>{value}</v></c>')
                continue
            k = index.setdefault(value, len(strings))
            if k == len(strings):
                strings.append(value)
            cells.append(f'<c r="{ref(r, c)}" t="s"><v>{k}</v></c>')
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    sheet = f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData>{"".join(body)}</sheetData></worksheet>'
    sst = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8"?><workbook {ns} {rel_ns}><sheets>'
        '<sheet name="List 1" sheetId="2" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", f'<?xml version="1.0" encoding="UTF-8"?><sst {ns}>{sst}</sst>')
    return Path(path)


def delineation(folder):
    rows = [
        ("Table with row headers in column A and column headers in row 3",),
        ("List 1. CORE BASED STATISTICAL AREAS (CBSAs), METROPOLITAN DIVISIONS, AND COMBINED STATISTICAL AREAS (CSAs)",),
        DELINEATION_HEADER,
        *DELINEATION_ROWS,
        (),
        *[(note,) for note in DELINEATION_FOOTNOTES],
    ]  # fmt: skip
    return write_xlsx(Path(folder) / "list1_2023.xlsx", rows)


def text_files(folder):
    """{name: path} for the gazetteer excerpts and SUB-EST."""
    folder = Path(folder)
    gaz_place = folder / "2025_Gaz_place_national.txt"
    gaz_place.write_text(GAZ_PLACE, encoding="utf-8")
    gaz_zcta = folder / "2025_Gaz_zcta_national.txt"
    gaz_zcta.write_text(GAZ_ZCTA, encoding="utf-8")
    pop = folder / "sub-est2025.csv"
    pop.write_bytes(SUB_EST.encode("latin-1"))
    return {"gazetteer_place": gaz_place, "gazetteer_zcta": gaz_zcta, "population": pop}


def aiannh(folder):
    fields = [("AIANNHCE", *C), ("AIANNHNS", *C), ("GEOIDFQ", *C), ("GEOID", *C), ("NAME", *C), ("NAMELSAD", *C),
              ("LSAD", *C), ("MTFCC", *C), ("ALAND", *N), ("AWATER", *N)]  # fmt: skip
    rows = [
        (box(36.5, -114.8, 36.7, -114.5), ("9001", "00000001", "2500000US9001", "9001", "Test",
         "Test Reservation", "86", "G2100", 500000000, 0)),
    ]  # fmt: skip
    return write_shapefile(Path(folder) / "cb_2025_us_aiannh_500k", fields, rows)


def all_inputs(folder):
    """Every input written into `folder`: {registry download name: path}."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return {
        "state": states(folder),
        "county": counties(folder),
        "place": places(folder),
        "cbsa": cbsa(folder),
        "csa": csa(folder),
        "zcta": zcta(folder),
        "aiannh": aiannh(folder),
        "delineation": delineation(folder),
        **text_files(folder),
    }
