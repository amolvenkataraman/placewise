import pytest
import shapefile  # pyshp: an independent writer, used only to build fixtures

from placewise.io import read_shapefile

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
UTM_PRJ = (
    'PROJCS["WGS_1984_UTM_Zone_17N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]],'
    'PROJECTION["Transverse_Mercator"]]'
)


def _write(tmp_path, prj=WGS84_PRJ):
    base = tmp_path / "zones"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as w:
        w.field("name", "C")
        w.field("rank", "N")
        # (x, y) = (lon, lat); per the spec outer rings run clockwise and holes counter-clockwise
        w.poly([[(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)], [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]])
        w.record("Square with hole", 1)
        w.poly([[(20, 0), (20, 2), (22, 2), (22, 0), (20, 0)], [(30, 0), (30, 2), (32, 2), (32, 0), (30, 0)]])
        w.record("Two islands", 2)
    if prj:
        (tmp_path / "zones.prj").write_text(prj)
    return base.with_suffix(".shp")


def test_reads_polygons_holes_parts_and_attributes(tmp_path):
    square, islands = read_shapefile(_write(tmp_path))
    assert square.properties == {"name": "Square with hole", "rank": 1}
    assert square.contains(2, 2) and not square.contains(5, 5)
    assert len(islands.outlines) == 2  # two outer rings: two polygons in one record
    assert islands.contains(1, 21) and islands.contains(1, 31) and not islands.contains(1, 25)


def test_without_prj_is_assumed_wgs84(tmp_path):
    assert len(read_shapefile(_write(tmp_path, prj=None))) == 2


def test_rejects_projected_shapefiles(tmp_path):
    with pytest.raises(ValueError, match="WGS84"):
        read_shapefile(_write(tmp_path, prj=UTM_PRJ))
