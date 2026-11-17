"""A tiny COD-AB-like package for the COD-AB pack tests, written with pyshp: the "cod-enhanced"
attribute schema (adm<n>_name, adm<n>_pcode, the parents' P-codes, valid_on, center_lat ...) on
invented lon/lat boxes in open Pacific water. Country "npl" so the registry entry and the claims
sectors exist; every unit, name and coordinate is made up.

        lon 170.0 ........ 170.5 ......... 171.0
lat 11  | P1: D11 (palikas A, B) | P2: D21 (C) |
lat 10  |       D12 (D, E: two records, an island) |

ADM1 comes in both plain and edge-matched ("_em") files; the "_em" one has a different name for P1
so the tests can tell which was read.
"""

import io
import itertools
import json
import zipfile
from pathlib import Path

import shapefile  # pyshp

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
VALID_ON = "2024-03-14"


def box(south, west, north, east, per_edge=1):
    """A clockwise ring of (lon, lat) (shapefile outer rings run clockwise), with per_edge - 1
    collinear points added on every edge for the simplification to remove."""
    corners = [(west, south), (west, north), (east, north), (east, south), (west, south)]
    out = []
    for (x0, y0), (x1, y1) in itertools.pairwise(corners):
        out += [(x0 + (x1 - x0) * k / per_edge, y0 + (y1 - y0) * k / per_edge) for k in range(per_edge)]
    return [*out, corners[0]]


# level -> [(rings, {field: value})]
ADM1 = [
    ([box(10, 170.0, 11, 170.5, per_edge=20)], {"adm1_name": "Province One", "adm1_pcode": "NP01"}),
    ([box(10, 170.5, 11, 171.0)], {"adm1_name": "Province Two", "adm1_pcode": "NP02"}),
]
ADM1_EM = [(rings, {**props, "adm1_name": props["adm1_name"] + " (em)"}) for rings, props in ADM1]
ADM2 = [
    (
        [box(10.5, 170.0, 11, 170.5)],
        {"adm2_name": "District Eleven", "adm2_pcode": "NP0101", "adm1_pcode": "NP01"},
    ),
    (
        [box(10, 170.0, 10.5, 170.5)],
        {"adm2_name": "District Twelve", "adm2_pcode": "NP0102", "adm1_pcode": "NP01"},
    ),
    (
        [box(10, 170.5, 11, 171.0)],
        {"adm2_name": "District TwentyOne", "adm2_pcode": "NP0201", "adm1_pcode": "NP02"},
    ),
]
ADM3 = [
    (
        [box(10.5, 170.0, 11, 170.25)],
        {"adm3_name": "Alpha", "adm3_pcode": "NP010101", "adm2_pcode": "NP0101"},
    ),
    (
        [box(10.5, 170.25, 11, 170.5)],
        {"adm3_name": "Bravo", "adm3_pcode": "NP010102", "adm2_pcode": "NP0101"},
    ),
    ([box(10, 170.5, 11, 171.0)], {"adm3_name": "Charlie", "adm3_pcode": "NP020101", "adm2_pcode": "NP0201"}),
    ([box(10, 170.0, 10.5, 170.3)], {"adm3_name": "Delta", "adm3_pcode": "NP010201", "adm2_pcode": "NP0102"}),
    ([box(10, 170.3, 10.5, 170.45)], {"adm3_name": "Echo", "adm3_pcode": "NP010202", "adm2_pcode": "NP0102"}),
    (
        [box(10.1, 170.46, 10.2, 170.49)],
        {"adm3_name": "Echo", "adm3_pcode": "NP010202", "adm2_pcode": "NP0102"},
    ),
]
# the Natural Earth claimant polygon the claims tests use: covers Bravo's east half and more
CLAIM = box(10.6, 170.4, 10.9, 170.6)


def write_level(directory, stem, records, n):
    """One level's .shp/.shx/.dbf/.prj/.cpg, in the enhanced schema."""
    base = Path(directory) / stem
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        for level in range(n, 0, -1):
            w.field(f"adm{level}_name", "C", 100)
            w.field(f"adm{level}_pcode", "C", 20)
        w.field("adm0_pcode", "C", 5)
        w.field("valid_on", "C", 10)
        w.field("center_lat", "N", 12, 6)
        for rings, props in records:
            values = []
            for level in range(n, 0, -1):
                values += [props.get(f"adm{level}_name", ""), props.get(f"adm{level}_pcode", "")]
            w.record(*values, "NP", VALID_ON, 10.5)
            w.poly([list(r) for r in rings])
    base.with_suffix(".prj").write_text(WGS84_PRJ)
    base.with_suffix(".cpg").write_text("UTF-8")
    return base.with_suffix(".shp")


def write_package(cache_dir, url):
    """The package zip as the build's cache would hold it after a full download (the zip and its
    fetch sidecar), so build_layers reads it without the network. Returns the zip path."""
    cache_dir = Path(cache_dir)
    staging = cache_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    write_level(staging, "npl_admin1", ADM1, 1)
    write_level(staging, "npl_admin1_em", ADM1_EM, 1)
    write_level(staging, "npl_admin2", ADM2, 2)
    write_level(staging, "npl_admin3", ADM3, 3)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for path in sorted(staging.iterdir()):
            z.write(path, path.name)
    name = url.rpartition("/")[2]
    target = cache_dir / name
    target.write_bytes(buffer.getvalue())
    (cache_dir / f"{name}.json").write_text(json.dumps({"url": url}))
    return target
