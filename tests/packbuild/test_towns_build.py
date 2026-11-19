"""The world-towns pack builder (packbuild.towns) on a synthetic GHS-SMOD zip and world pack."""

import json
import struct
import zipfile

import numpy as np
from ghsl_kit import write_tiff

from packbuild import towns
from packbuild.projection import WORLD_MOLLWEIDE
from placewise.engine import Geocoder
from placewise.model import Feature, Outline, Relation
from placewise.packs import LayerData, open_pack, write_pack

# 1 km cells, top-left corner (-1000, 3000) m: Mollweide's centre, a few km of open ocean
PICTURE = [
    "CCCC......",
    "CCCC....DD",
    "..........",
    "DD........",  # in the "US" box: left out
]
VALUES = {"C": 30, "D": 23, ".": 11}
STEM = "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000"


def lonlat(x, y):
    lon, lat = WORLD_MOLLWEIDE.inverse(x, y)
    return float(lat), float(lon)


def cell_centre(row, col):
    return lonlat(-1000 + (col + 0.5) * 1000, 3000 - (row + 0.5) * 1000)


def box(south, west, north, east):
    return Feature((Outline((((south, west), (south, east), (north, east), (north, west)),)),))


def dbf(rows):
    """A dBASE file of (POP_2020, PWCentr_X, PWCentr_Y) rows."""
    fields = [("POP_2020", 16, 6), ("PWCentr_X", 19, 6), ("PWCentr_Y", 19, 6)]
    header_len, record_len = 32 + 32 * len(fields) + 1, 1 + sum(f[1] for f in fields)
    out = bytearray(struct.pack("<BBBBIHH20x", 3, 126, 1, 1, len(rows), header_len, record_len))
    for name, size, decimals in fields:
        out += name.encode().ljust(11, b"\0") + b"N" + bytes(4) + bytes([size, decimals]) + bytes(14)
    out += b"\r"
    for row in rows:
        out += b" " + b"".join(f"{v:{f[1]}.{f[2]}f}".encode() for v, f in zip(row, fields, strict=True))
    return bytes(out + b"\x1a")


def write_zip(path):
    grid = np.array([[VALUES[c] for c in line] for line in PICTURE], dtype=np.int16)
    uc = dbf([(150_000.0, 1000.0, 2000.0)])
    duc = dbf([(7_000.0, 7500.0, 1500.0)])
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{STEM}_V2_0.tif", write_tiff(grid, tile=(8, 8), compression=5, predictor=2, big=True))
        z.writestr(f"{STEM}_UC_V2_0.dbf", uc)
        z.writestr(f"{STEM}_DUC_V2_0.dbf", duc)
    return path


def write_world(out):
    us_top = cell_centre(2, 0)[0] - 0.004  # rows 3 and below
    countries = LayerData(
        "countries", "polygon",
        {"id": ["iso:XA", "iso:US"], "name": ["Alphaland", "United States"], "iso2": ["XA", "US"],
         "iso3": ["XAA", "USA"], "adm0_a3": ["XAA", "USA"]},
        ("synthetic",), features=[box(us_top, -0.1, 0.1, 0.1), box(-0.1, -0.1, us_top, 0.1)],
    )  # fmt: skip
    places = [("geonames:1", "Centreville", "XA", 140_000, "PPLA", cell_centre(0, 1)),
              ("geonames:2", "Eastby", "XA", 6_000, "PPL", cell_centre(1, 9)),
              ("geonames:3", "Westus", "US", 5_000, "PPL", cell_centre(3, 0))]  # fmt: skip
    cities = LayerData(
        "cities", "point",
        {"id": [p[0] for p in places], "name": [p[1] for p in places], "country": [p[2] for p in places],
         "population": np.array([p[3] for p in places]), "feature_code": [p[4] for p in places]},
        ("synthetic",), lat=np.array([p[5][0] for p in places]), lon=np.array([p[5][1] for p in places]),
    )  # fmt: skip
    return write_pack(out, "world", "2026.11", [countries, cities], created="2026-11-18T00:00:00Z")


def test_build_writes_the_pack(tmp_path, monkeypatch):
    archive = write_zip(tmp_path / f"{STEM}_V2_0.zip")
    monkeypatch.setattr(towns, "fetch", lambda *a, **k: archive)
    world = write_world(tmp_path / "out")
    path = towns.build(tmp_path, tmp_path / "out", "2026.11", tolerance=0)
    meta = json.loads((path / "pack.json").read_text())
    about = (meta["name"], meta["kind"], meta["covers"], meta["requires"])
    assert about == ("world-towns", "towns", ["*"], ["world"])
    layer = open_pack(path)["towns"]
    assert layer.column("id").tolist() == ["ghs:XA:1", "ghs:XA:2"]
    assert layer.column("class").tolist() == ["centre", "town"]
    assert layer.column("population").tolist() == [150_000, 7_000]
    geo = Geocoder(packs=[world, path])
    r = geo.lookup(*cell_centre(1, 3))
    assert r.city.name == "Centreville" and r.matches["city"].relation == Relation.WITHIN
    assert geo.lookup(*cell_centre(1, 8)).city.name == "Eastby"
