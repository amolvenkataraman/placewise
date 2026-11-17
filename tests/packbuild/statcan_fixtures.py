"""Tiny Statistics Canada-like boundary files for the Canada pack tests, written with pyshp.

Attribute names and values follow the 2021 Census cartographic boundary files (real UIDs, names and
types for Toronto, Mississauga, Milton, Ottawa, Gatineau and Banff); the shapes are coarse
lat/lon boxes, projected into Statistics Canada Lambert (EPSG:3347) as the real files are. The
population CSVs beside them in data/ are excerpts of the real tables 98-10-0002-01, 98-10-0005-01
and 98-10-0019-01 (including Listuguj, whose count is suppressed: "..").

Deliberate tweaks: Toronto's ring has extra collinear points and a 3 m island (for simplification);
Banff National Park's CSD name has StatCan's double space ("No.  9", as in "Division No.  1") so
whitespace clean-up is exercised; the Banff town CSD is a hole in it, as in the real files.
"""

import itertools
import json
import re
from pathlib import Path

import numpy as np
import shapefile  # pyshp

from packbuild.projection import STATCAN_LAMBERT

DATA = Path(__file__).parent / "data"

# what ArcGIS writes for EPSG:3347 (the .prj inside StatCan's 2021 zips)
STATCAN_PRJ = (
    'PROJCS["PCS_Lambert_Conformal_Conic",GEOGCS["GCS_North_American_1983",'
    'DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Lambert_Conformal_Conic"],PARAMETER["False_Easting",6200000.0],'
    'PARAMETER["False_Northing",3000000.0],PARAMETER["Central_Meridian",-91.86666666666666],'
    'PARAMETER["Standard_Parallel_1",49.0],PARAMETER["Standard_Parallel_2",77.0],'
    'PARAMETER["Latitude_Of_Origin",63.390675],UNIT["Meter",1.0]]'
)

# public places used by the tests: (lat, lon)
CN_TOWER = (43.6426, -79.3871)
MISSISSAUGA = (43.5890, -79.6441)
MILTON_GO = (43.5250, -79.8820)
PARLIAMENT_HILL = (45.4236, -75.7009)
GATINEAU = (45.4765, -75.7013)
LAKE_LOUISE = (51.4254, -116.1773)
BANFF = (51.1784, -115.5708)


def box(south, west, north, east):
    """A clockwise ring of (lat, lon), as shapefiles want outer rings (holes run the other way)."""
    return [(south, west), (north, west), (north, east), (south, east), (south, west)]


def dense(ring, per_edge):
    """The same ring with `per_edge - 1` extra collinear (in Lambert metres) points on every edge."""
    out = []
    for a, b in itertools.pairwise(ring):
        ax, ay = STATCAN_LAMBERT.forward(a[1], a[0])
        bx, by = STATCAN_LAMBERT.forward(b[1], b[0])
        for k in range(per_edge):
            f = k / per_edge
            lon, lat = STATCAN_LAMBERT.inverse(ax + f * (bx - ax), ay + f * (by - ay))
            out.append((float(lat), float(lon)))
    return [*out, out[0]]


def lambert(ring):
    """[(x, y), ...] in EPSG:3347 metres for a ring of (lat, lon)."""
    lat, lon = np.array(ring, dtype=float).T
    x, y = STATCAN_LAMBERT.forward(lon, lat)
    return list(zip(x.tolist(), y.tolist(), strict=True))


def tiny_island(lat, lon, size_m=3.0):
    """A clockwise triangle a few metres across: smaller than any simplification tolerance."""
    x, y = STATCAN_LAMBERT.forward(lon, lat)
    pts = [(x, y), (x, y + size_m), (x + size_m, y), (x, y)]
    out = []
    for px, py in pts:
        lo, la = STATCAN_LAMBERT.inverse(px, py)
        out.append((float(la), float(lo)))
    return out


C = ("C", 100)
PR_FIELDS = [
    ("PRUID", "C", 2),
    ("DGUID", "C", 21),
    ("PRNAME", *C),
    ("PRENAME", *C),
    ("PRFNAME", *C),
    ("PREABBR", "C", 10),
    ("PRFABBR", "C", 10),
    ("LANDAREA", "N", 17, 4),
]
ONTARIO = [
    (41.5, -95.2),
    (56.9, -95.2),
    (56.9, -79.5),
    (45.45, -79.5),
    (45.45, -74.3),
    (41.5, -74.3),
    (41.5, -95.2),
]
PROVINCES = [
    ([ONTARIO], ("35", "2021A000235", "Ontario", "Ontario", "Ontario", "Ont.", "Ont.", 892411.7626)),
    (
        [box(45.45, -79.5, 62.6, -57.1)],
        ("24", "2021A000224", "Quebec / Québec", "Quebec", "Québec", "Que.", "Qc", 1298599.7477),
    ),
    (
        [box(49.0, -120.0, 60.0, -110.0)],
        ("48", "2021A000248", "Alberta", "Alberta", "Alberta", "Alta.", "Alb.", 634658.2668),
    ),
]

CD_FIELDS = [
    ("CDUID", "C", 4),
    ("DGUID", "C", 21),
    ("CDNAME", *C),
    ("CDTYPE", "C", 3),
    ("LANDAREA", "N", 17, 4),
    ("PRUID", "C", 2),
]
TORONTO = box(43.58, -79.62, 43.86, -79.11)
PEEL = box(43.55, -79.80, 43.95, -79.62)
HALTON = box(43.30, -80.20, 43.55, -79.62)
OTTAWA = box(45.00, -76.40, 45.45, -75.20)
GATINEAU_BOX = box(45.45, -76.00, 45.70, -75.40)
DIVISION_15 = box(50.50, -118.00, 52.50, -114.50)
CDS = [
    ([TORONTO], ("3520", "2021A00033520", "Toronto", "CDR", 631.0983, "35")),
    ([PEEL], ("3521", "2021A00033521", "Peel", "RM", 1247.4494, "35")),
    ([HALTON], ("3524", "2021A00033524", "Halton", "RM", 965.7063, "35")),
    ([OTTAWA], ("3506", "2021A00033506", "Ottawa", "CDR", 2788.1967, "35")),
    ([GATINEAU_BOX], ("2481", "2021A00032481", "Gatineau", "TÉ", 341.8414, "24")),
    ([DIVISION_15], ("4815", "2021A00034815", "Division No. 15", "CDR", 28270.1441, "48")),
]

CSD_FIELDS = [
    ("CSDUID", "C", 7),
    ("DGUID", "C", 21),
    ("CSDNAME", *C),
    ("CSDTYPE", "C", 3),
    ("LANDAREA", "N", 17, 4),
    ("PRUID", "C", 2),
]
BANFF_TOWN = box(51.15, -115.62, 51.20, -115.52)
CSDS = [
    # Toronto: dense edges (simplify to 4 corners) and a 3 m island in the lake (dropped)
    (
        [dense(TORONTO, 50), tiny_island(43.57, -79.30)],
        ("3520005", "2021A00053520005", "Toronto", "C", 631.0983, "35"),
    ),
    ([PEEL], ("3521005", "2021A00053521005", "Mississauga", "CY", 292.7442, "35")),
    ([box(43.40, -80.05, 43.55, -79.75)], ("3524009", "2021A00053524009", "Milton", "T", 363.8308, "35")),
    ([OTTAWA], ("3506008", "2021A00053506008", "Ottawa", "CV", 2788.1967, "35")),
    ([GATINEAU_BOX], ("2481017", "2021A00052481017", "Gatineau", "V", 341.8414, "24")),
    # Banff National Park, with the town of Banff as a hole (counter-clockwise)
    (
        [box(50.70, -117.00, 52.20, -115.00), BANFF_TOWN[::-1]],
        ("4815032", "2021A00054815032", "Improvement District No.  9 Banff", "ID", 6751.0859, "48"),
    ),
    ([BANFF_TOWN], ("4815035", "2021A00054815035", "Banff", "T", 4.0834, "48")),
    # an incompletely enumerated reserve: its population is suppressed ("..") in 98-10-0002-01
    ([box(48.00, -66.80, 48.05, -66.70)], ("2406804", "2021A00052406804", "Listuguj", "IRI", 37.6, "24")),
]

CMA_FIELDS = [
    ("CMAUID", "C", 3),
    ("CMAPUID", "C", 5),
    ("DGUID", "C", 21),
    ("CMANAME", *C),
    ("CMATYPE", "C", 1),
    ("LANDAREA", "N", 17, 4),
    ("PRUID", "C", 2),
]
CMAS = [
    (
        [box(43.40, -80.10, 44.30, -79.00)],
        ("535", "35535", "2021S050535535", "Toronto", "B", 5902.7499, "35"),
    ),
    (
        [box(44.90, -76.40, 45.45, -75.20)],
        (
            "505",
            "35505",
            "2021S050535505",
            "Ottawa - Gatineau (Ontario part / partie de l'Ontario)",
            "B",
            4665.1591,
            "35",
        ),
    ),
    (
        [box(45.45, -76.20, 45.90, -75.20)],
        (
            "505",
            "24505",
            "2021S050524505",
            "Ottawa - Gatineau (partie du Québec / Quebec part)",
            "B",
            3381.8311,
            "24",
        ),
    ),
    (
        [box(51.00, -115.45, 51.15, -115.20)],
        ("828", "48828", "2021S050648828", "Canmore", "D", 68.4694, "48"),
    ),
]

FSA_FIELDS = [
    ("CFSAUID", "C", 3),
    ("DGUID", "C", 21),
    ("PRUID", "C", 2),
    ("PRNAME", *C),
    ("LANDAREA", "N", 17, 4),
]
FSAS = [
    ([box(43.63, -79.40, 43.65, -79.37)], ("M5J", "2021A0011M5J", "35", "Ontario", 4.1369)),
    ([box(43.48, -79.95, 43.56, -79.80)], ("L9T", "2021A0011L9T", "35", "Ontario", 82.9492)),
    ([box(45.40, -75.72, 45.43, -75.69)], ("K1R", "2021A0011K1R", "35", "Ontario", 3.7073)),
    ([box(45.46, -75.72, 45.50, -75.68)], ("J8T", "2021A0011J8T", "24", "Quebec / Québec", 18.0206)),
    ([box(51.30, -116.50, 51.60, -116.00)], ("T0L", "2021A0011T0L", "48", "Alberta", 28134.5502)),
    ([BANFF_TOWN], ("T1L", "2021A0011T1L", "48", "Alberta", 4.0833)),
]

# zip stem -> (fields, rows), named as the real 2021 downloads
LAYERS = {
    "lpr_000b21a_e": (PR_FIELDS, PROVINCES),
    "lcd_000b21a_e": (CD_FIELDS, CDS),
    "lcsd000b21a_e": (CSD_FIELDS, CSDS),
    "lcma000b21a_e": (CMA_FIELDS, CMAS),
    "lfsa000b21a_e": (FSA_FIELDS, FSAS),
}
POPULATION = {
    "98100002": DATA / "98100002.csv",
    "98100005": DATA / "98100005.csv",
    "98100019": DATA / "98100019.csv",
}


def write_shapefile(directory, stem, prj=STATCAN_PRJ):
    """Write `<directory>/<stem>.shp` (+ .shx .dbf .prj .cpg) from LAYERS; returns the .shp path."""
    fields, rows = LAYERS[stem]
    base = Path(directory) / stem
    base.parent.mkdir(parents=True, exist_ok=True)
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        for field in fields:
            w.field(*field)
        for rings, record in rows:
            w.poly([lambert(ring) for ring in rings])
            w.record(*record)
    if prj is not None:
        base.with_suffix(".prj").write_text(prj)
    base.with_suffix(".cpg").write_text("UTF-8")
    return base.with_suffix(".shp")


def service_features(stem):
    """The layer's records as the map service returns them: Esri JSON, outSR 3347, OBJECTID from 1,
    SHAPE_Length the perimeter in metres."""
    fields, rows = LAYERS[stem]
    names = [f[0] for f in fields]
    out = []
    for i, (rings, record) in enumerate(rows):
        xy = [np.array(lambert(ring)) for ring in rings]
        perimeter = sum(float(np.hypot(*np.diff(r, axis=0).T).sum()) for r in xy)
        attributes = {"OBJECTID": i + 1, **dict(zip(names, record, strict=True)), "SHAPE_Length": perimeter}
        out.append({"attributes": attributes, "geometry": {"rings": [r.tolist() for r in xy]}})
    return out


def service_page(features):
    return json.dumps(
        {
            "geometryType": "esriGeometryPolygon",
            "spatialReference": {"wkid": 3347, "latestWkid": 3347},
            "features": features,
        }
    )


def service_pages(stem, page_size=3):
    """The layer as a few query pages, for reading tests."""
    features = service_features(stem)
    pages = [service_page(features[i : i + page_size]) for i in range(0, len(features), page_size)]
    return pages, len(features)


class FakeService:
    """Answers the map service's requests for every fixture layer from memory. `slow` maps a layer
    stem to OBJECTIDs that time out (HTTP 504, or a JSON error) unless asked for alone and generalised."""

    def __init__(self, service_url, slow=None, json_errors=False):
        self.service_url = service_url
        self.json_errors = (
            json_errors  # fail as HTTP 200 + {"error": {"code": 500}}, as the service also does
        )
        self.stems = list(LAYERS)
        self.slow = slow or {}
        self.requests = []

    def __call__(self, url, timeout=120):
        import urllib.error
        import urllib.parse

        self.requests.append(url)
        base, _, query = url.partition("?")
        params = dict(urllib.parse.parse_qsl(query))
        if base == self.service_url:
            names = [{"id": i, "name": f"{s[1:4].upper()} - {s[:10]}s_e"} for i, s in enumerate(self.stems)]
            return json.dumps({"layers": names}).encode()
        stem = self.stems[int(base.rsplit("/", 2)[-2])]
        features = service_features(stem)
        if params.get("returnGeometry") == "false":
            start, count = int(params["resultOffset"]), int(params["resultRecordCount"])
            rows = [
                {"attributes": {k: f["attributes"][k] for k in ("OBJECTID", "SHAPE_Length")}}
                for f in features
            ]
            chunk = rows[start : start + count]
            return json.dumps(
                {"features": chunk, "exceededTransferLimit": start + count < len(rows)}
            ).encode()
        assert params["outSR"] == "3347" and params["f"] == "json" and params["outFields"] == "*"
        low, high = (
            int(v) for v in re.fullmatch(r"OBJECTID>=(\d+) AND OBJECTID<=(\d+)", params["where"]).groups()
        )
        slow = [oid for oid in self.slow.get(stem, ()) if low <= oid <= high]
        if slow and (high > low or "maxAllowableOffset" not in params):
            if self.json_errors:
                return json.dumps(
                    {"error": {"code": 500, "message": "Error performing query operation"}}
                ).encode()
            raise urllib.error.HTTPError(url, 504, "Gateway Time-out", {}, None)
        return service_page([f for f in features if low <= f["attributes"]["OBJECTID"] <= high]).encode()
