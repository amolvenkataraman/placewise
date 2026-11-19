"""Named town and city outlines from a synthetic GHS-SMOD grid (packbuild.sources.ghsl.towns).

The grid's cells are 1 km in Mollweide, top-left corner at (-1000, 3000) m. Columns 0-5 are in
country AA, 6-9 in BB, and row 7 in CC (left out); C = urban centre, D/S = dense / semi-dense town:

    row 0   C C C C C C C C . .     one centre crossing the AA/BB border, with a one-cell hole
    row 1   C . C C C C C C . .
    row 2   C C C C . . . . . .
    row 3   . . . . . . . . D D     town in BB named by a place in its cells
    row 4   S S . . . . . . . .     town in AA named by a place one cell outside it (row 5)
    row 5   . . . . . . . . . D     town in BB with no place: dropped
    row 7   D D . . . . . . . .     town in CC: left out
"""

import numpy as np
import pytest
from ghsl_kit import write_tiff

from packbuild.projection import WORLD_MOLLWEIDE
from packbuild.sources.ghsl.geotiff import GeoTiff
from packbuild.sources.ghsl.towns import outlines

PICTURE = [
    "CCCCCCCC..",
    "C.CCCCCC..",
    "CCCC......",
    "........DD",
    "SS........",
    ".........D",
    "..........",
    "DD........",
]
VALUES = {"C": 30, "D": 23, "S": 22, ".": 11}


def grid():
    return np.array([[VALUES[ch] for ch in line] for line in PICTURE], dtype=np.int16)


def centre(row, col):
    lon, lat = WORLD_MOLLWEIDE.inverse(-1000 + (col + 0.5) * 1000, 3000 - (row + 0.5) * 1000)
    return float(lat), float(lon)


BORDER_LON = float(WORLD_MOLLWEIDE.inverse(5000.0, 0.0)[0])  # the edge between columns 5 and 6
CC_LAT = float(centre(6, 0)[0] + centre(7, 0)[0]) / 2


def country_of(lon, lat):
    return np.where(lat < CC_LAT, "CC", np.where(lon < BORDER_LON, "AA", "BB"))


# id, name, population, country, feature code, cell
PLACES = [
    ("geonames:1", "Bigtown", 500_000, "AA", "PPLA", (0, 1)),
    ("geonames:2", "Bigtown Centre", 900_000, "AA", "PPLX", (0, 3)),  # a section: never a name
    ("geonames:3", "Smallside", 20_000, "AA", "PPL", (2, 2)),
    ("geonames:4", "Borderville", 80_000, "BB", "PPL", (1, 7)),
    ("geonames:5", "Eastdale", 9_000, "BB", "PPL", (3, 9)),
    ("geonames:6", "Halo", 3_000, "AA", "PPL", (5, 0)),
    ("geonames:7", "Leftout", 5_000, "CC", "PPL", (7, 0)),
    ("geonames:8", "Strayton", 4_000, "AA", "PPL", (1, 6)),  # AA's place in BB's cells: not its name
]


def cities():
    points = [centre(*p[5]) for p in PLACES]
    return {
        "id": [p[0] for p in PLACES], "name": [p[1] for p in PLACES],
        "population": np.array([p[2] for p in PLACES]), "country": [p[3] for p in PLACES],
        "feature_code": [p[4] for p in PLACES],
        "lat": np.array([p[0] for p in points]), "lon": np.array([p[1] for p in points]),
    }  # fmt: skip


def build(**options):
    tif = GeoTiff(write_tiff(grid(), tile=(4, 4), compression=5, predictor=2))
    return outlines(tif, country_of, cities(), excluded=("CC",), **options)


def test_outlines_are_cut_at_borders_named_and_ordered():
    features, columns = build()
    assert columns["id"] == ["ghs:AA:1", "ghs:BB:4", "ghs:BB:5", "ghs:AA:6"]
    assert columns["name"] == ["Bigtown", "Borderville", "Eastdale", "Halo"]
    assert columns["geonames"] == ["geonames:1", "geonames:4", "geonames:5", "geonames:6"]
    assert columns["class"] == ["centre", "centre", "town", "town"]
    assert columns["country"] == ["AA", "BB", "BB", "AA"]
    assert columns["population"].tolist() == [-1, -1, -1, -1]
    assert [f.id for f in features] == columns["id"]


def test_small_holes_are_filled_and_the_outline_follows_the_cells():
    features, _ = build(tolerance=0)
    bigtown = features[0]
    assert len(bigtown.outlines) == 1 and len(bigtown.outlines[0].rings) == 1  # the hole is filled
    lats = [p[0] for p in bigtown.outlines[0].rings[0]]
    lons = [p[1] for p in bigtown.outlines[0].rings[0]]
    assert min(lons) == pytest.approx(float(WORLD_MOLLWEIDE.inverse(-1000.0, 2500.0)[0]), abs=1e-9)
    assert max(lons) == pytest.approx(BORDER_LON, abs=1e-6)
    assert max(lats) == pytest.approx(float(WORLD_MOLLWEIDE.inverse(0.0, 3000.0)[1]), abs=1e-9)


def test_population_only_for_whole_clusters():
    def mollweide(row, col):
        return -1000 + (col + 0.5) * 1000, 3000 - (row + 0.5) * 1000

    points = [
        (0, 120_000.0, *mollweide(0, 2)),
        (1, 15_000.0, *mollweide(3, 8)),
        (1, 4_000.0, *mollweide(7, 1)),
    ]
    centroids = tuple(np.array(v) for v in zip(*points, strict=True))
    tif = GeoTiff(write_tiff(grid(), tile=(4, 4), compression=5, predictor=2))
    _, columns = outlines(tif, country_of, cities(), centroids=centroids, excluded=("CC",))
    # the centre is cut by the border: no population; Eastdale is its whole cluster
    assert columns["population"].tolist() == [-1, -1, 15_000, -1]
