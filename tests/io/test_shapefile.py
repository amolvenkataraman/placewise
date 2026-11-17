import pytest
import shapefile  # pyshp: an independent writer, used only to build fixtures

from placewise.io import read_shapefile
from placewise.io.shapefile import prj_datum

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


def test_strips_nul_padding_in_text_fields(tmp_path):
    # Natural Earth pads .dbf text with NUL bytes instead of the spaces the format specifies
    shp = _write(tmp_path)
    dbf = shp.with_suffix(".dbf")
    data = dbf.read_bytes()
    padded = b"Two islands".ljust(50)
    assert padded in data
    dbf.write_bytes(data.replace(padded, b"Two islands".ljust(50, b"\x00")))
    assert read_shapefile(shp)[1].properties["name"] == "Two islands"


NAD83_PRJ = (
    'GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137,'
    '298.257222101]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)
NAD27_PRJ = (
    'GEOGCS["GCS_North_American_1927",DATUM["D_North_American_1927",SPHEROID["Clarke_1866",6378206.4,'
    '294.9786982]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
)


def test_nad83_is_refused_unless_accepted_and_then_read_unchanged(tmp_path):
    # NAD83 and WGS84 differ by 1-2 m in North America: below the generalisation of most boundary files
    shp = _write(tmp_path, prj=NAD83_PRJ)
    with pytest.raises(ValueError, match="not WGS84"):
        read_shapefile(shp)
    square, _ = read_shapefile(shp, accept_nad83=True)
    assert square.outlines[0].rings[0][1] == (10.0, 0.0)  # coordinates pass through untransformed
    other = tmp_path / "nad27"
    other.mkdir()
    with pytest.raises(ValueError, match="datum"):  # other datums would need a real datum shift
        read_shapefile(_write(other, prj=NAD27_PRJ), accept_nad83=True)


@pytest.mark.parametrize(
    ("prj", "datum"),
    [
        (WGS84_PRJ, "wgs84"),
        (NAD83_PRJ, "nad83"),
        ('GEOGCS["NAD83",DATUM["North_American_Datum_1983",SPHEROID["GRS 1980"]]]', "nad83"),
        ('GEOGCS["NAD83(2011)",DATUM["NAD83_National_Spatial_Reference_System_2011"]]', "nad83"),
        ('GEOGCS["NAD83(CSRS)",DATUM["D_North_American_1983_CSRS"]]', "nad83"),
    ],
)
def test_prj_datum(prj, datum):
    assert prj_datum(prj) == datum


@pytest.mark.parametrize(
    ("prj", "message"), [(NAD27_PRJ, "datum"), (UTM_PRJ, "projected"), ("junk", "datum")]
)
def test_prj_datum_refuses_anything_else(prj, message):
    with pytest.raises(ValueError, match=message):
        prj_datum(prj)
