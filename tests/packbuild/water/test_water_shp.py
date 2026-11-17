"""packbuild.sources.water.shp: shapefile records and dBASE columns as numpy, for big or line files."""

import math

import numpy as np
import pytest
import shapefile  # pyshp, to write fixtures

from packbuild.sources.water import shp as _shp


def _lines(base):
    with shapefile.Writer(str(base), shapeType=shapefile.POLYLINE) as w:
        w.field("name", "C", 20)
        w.field("rank", "N", 4, 0)
        w.field("area", "N", 8, 2)
        w.line([[(10.0, 1.0), (11.0, 2.0), (12.0, 2.5)]])
        w.record("Ganges", 3, 1.5)
        w.line([[(0.0, 0.0), (1.0, 0.0)], [(5.0, 5.0), (6.0, 6.0)]])
        w.record("Twin", None, None)
    return base.with_suffix(".shp")


def test_line_records_have_their_parts_as_lon_lat_arrays(tmp_path):
    shapes = list(_shp.read_shapes(_lines(tmp_path / "rivers")))
    assert len(shapes) == 2
    first, second = shapes
    assert len(first) == 1 and first[0].tolist() == [[10.0, 1.0], [11.0, 2.0], [12.0, 2.5]]
    assert [p.tolist() for p in second] == [[[0.0, 0.0], [1.0, 0.0]], [[5.0, 5.0], [6.0, 6.0]]]


def test_polygon_records_and_null_shapes(tmp_path):
    base = tmp_path / "lakes"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as w:
        w.field("name", "C", 10)
        w.poly([[(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]])
        w.record("a")
        w.null()
        w.record("b")
    shapes = list(_shp.read_shapes(base.with_suffix(".shp")))
    assert shapes[1] is None
    assert shapes[0][0].shape == (5, 2)


def test_limit_and_truncated_files_stop_at_whole_records(tmp_path):
    shp = _lines(tmp_path / "rivers")
    assert len(list(_shp.read_shapes(shp, limit=1))) == 1
    data = shp.read_bytes()
    cut = tmp_path / "cut.shp"
    cut.write_bytes(data[:-10])  # the second record is incomplete
    assert len(list(_shp.read_shapes(cut))) == 1


def test_points_and_other_types_are_refused(tmp_path):
    base = tmp_path / "pts"
    with shapefile.Writer(str(base), shapeType=shapefile.POINT) as w:
        w.field("name", "C", 10)
        w.point(1, 2)
        w.record("a")
    with pytest.raises(ValueError, match="shape type 1"):
        list(_shp.read_shapes(base.with_suffix(".shp")))


def test_dbf_columns_are_stripped_text(tmp_path):
    shp = _lines(tmp_path / "rivers")
    columns = _shp.read_dbf(shp.with_suffix(".dbf"))
    assert columns["name"] == ["Ganges", "Twin"]
    rank = _shp.numbers(columns["rank"])  # pyshp writes a null number as stars, as NE does
    assert rank[0] == 3 and math.isnan(rank[1])
    assert _shp.read_dbf(shp.with_suffix(".dbf"), limit=1)["name"] == ["Ganges"]
    assert set(_shp.read_dbf(shp.with_suffix(".dbf"), fields=("name",))) == {"name"}


def test_numbers_tolerate_blanks_and_overflow_stars():
    # Natural Earth's supplements write "**********" where a number overflowed its field
    values = _shp.numbers(["3", "", "**********", "1.5", " 7 "])
    assert values[0] == 3 and values[3] == 1.5 and values[4] == 7
    assert math.isnan(values[1]) and math.isnan(values[2])
    assert values.dtype == np.float64


def test_dbf_text_with_nul_padding_and_utf8(tmp_path):
    base = tmp_path / "names"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYLINE, encoding="utf-8") as w:
        w.field("name", "C", 20)
        w.line([[(0.0, 0.0), (1.0, 1.0)]])
        w.record("Pääjärvi")
    dbf = base.with_suffix(".dbf")
    raw = bytearray(dbf.read_bytes())
    raw[-2] = 0  # Natural Earth pads with NUL bytes rather than spaces
    dbf.write_bytes(bytes(raw))
    assert _shp.read_dbf(dbf)["name"] == ["Pääjärvi"]


def test_record_ends_from_the_index_cut_the_shp_at_whole_records(tmp_path):
    shp = _lines(tmp_path / "rivers")
    ends = _shp.record_ends(shp.with_suffix(".shx"))
    assert len(ends) == 2 and ends[-1] == len(shp.read_bytes())
    cut = tmp_path / "first.shp"
    cut.write_bytes(shp.read_bytes()[: ends[0]])
    assert len(list(_shp.read_shapes(cut))) == 1
