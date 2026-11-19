"""packbuild.gpkg: polygon rows out of a GeoPackage, any WKB byte order, Z dropped."""

import numpy as np
import pytest
from gpkg_kit import gp_blob, wkb_multipolygon, wkb_polygon, write_gpkg

from packbuild import gpkg

SQUARE = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)]
HOLE = [(2.0, 2.0), (4.0, 2.0), (4.0, 4.0), (2.0, 2.0)]
FAR = [(100.0, 100.0), (100.0, 110.0), (110.0, 100.0), (100.0, 100.0)]


def test_feature_tables_and_rows(tmp_path):
    path = write_gpkg(tmp_path / "a.gpkg", "sites", ("code", "name"), [
        ("A1", "Alpha", gp_blob(wkb_polygon([SQUARE, HOLE]))),
        ("B2", "Beta", gp_blob(wkb_multipolygon([[SQUARE], [FAR]], order=">"), envelope=None)),
        ("C3", "Gamma", None),
        ("D4", "Delta", gp_blob(wkb_polygon([]), empty=True)),
    ])  # fmt: skip
    assert gpkg.feature_tables(path) == {"sites": ("geom", 3035)}
    rows = list(gpkg.read_polygons(path, "sites", ("code", "name")))
    names = [("A1", "Alpha"), ("B2", "Beta"), ("C3", "Gamma"), ("D4", "Delta")]
    assert [a for a, _ in rows] == [{"code": c, "name": n} for c, n in names]
    alpha, beta = rows[0][1], rows[1][1]
    assert len(alpha) == 1 and [len(r) for r in alpha[0]] == [5, 4]
    np.testing.assert_array_equal(alpha[0][1], np.array(HOLE))
    assert len(beta) == 2  # big-endian multipolygon, no envelope
    np.testing.assert_array_equal(beta[1][0], np.array(FAR))
    assert rows[2][1] == [] and rows[3][1] == []


def test_z_ordinates_are_dropped():
    polys = gpkg.polygons(gp_blob(wkb_multipolygon([[SQUARE]], z=True)))
    assert polys[0][0].shape == (5, 2)
    np.testing.assert_array_equal(polys[0][0], np.array(SQUARE))


def test_other_geometry_types_are_refused():
    point = b"\x01" + (1).to_bytes(4, "little") + bytes(16)
    with pytest.raises(ValueError, match="WKB geometry type 1"):
        gpkg.polygons(gp_blob(point))
    with pytest.raises(ValueError, match="magic"):
        gpkg.polygons(b"XX" + bytes(10))


def test_a_condition_picks_rows(tmp_path):
    path = write_gpkg(tmp_path / "b.gpkg", "sites", ("code", "kind"), [
        ("A1", "polygon", gp_blob(wkb_polygon([SQUARE]))),
        ("B2", "point", gp_blob(b"\x01" + (1).to_bytes(4, "little") + bytes(16))),  # never parsed
    ])  # fmt: skip
    rows = list(gpkg.read_polygons(path, "sites", ("code",), where="kind = 'polygon'"))
    assert [a["code"] for a, _ in rows] == ["A1"]
