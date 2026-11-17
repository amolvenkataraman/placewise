"""packbuild.sources.water.shapes: lon/lat parts into Features: simplified in metres, lines as
zero-area rings, the pole edge snapped to ±180."""

import numpy as np
import pytest

from packbuild.sources.water import shapes as ws
from placewise.packs import LayerData, open_pack, write_pack


def _square(lon0, lat0, size, n=40, clockwise=True):
    """A square ring with n points per side (lon, lat), clockwise like a shapefile shell."""
    t = np.linspace(0, size, n, endpoint=False)
    side = [(lon0 + s, lat0) for s in t] + [(lon0 + size, lat0 + s) for s in t]
    side += [(lon0 + size - s, lat0 + size) for s in t] + [(lon0, lat0 + size - s) for s in t]
    ring = np.array([*side, side[0]])
    return ring if not clockwise else ring[::-1]


def test_polygon_feature_simplifies_in_metres_and_keeps_holes():
    shell = _square(10.0, 50.0, 1.0)
    hole = _square(10.4, 50.4, 0.2, clockwise=False)
    f = ws.polygon_feature([shell, hole], tolerance_m=50, fid="lake:1")
    assert f.id == "lake:1" and len(f.outlines) == 1
    rings = f.outlines[0].rings
    assert len(rings) == 2  # the hole stays a hole
    assert len(rings[0]) == 4  # collinear points on each side go: only the corners stay
    assert f.contains(50.2, 10.2) and not f.contains(50.5, 10.5)


def test_polygon_feature_with_no_tolerance_keeps_every_vertex():
    f = ws.polygon_feature([_square(0.0, 0.0, 1.0, n=5)], tolerance_m=0, fid="x")
    assert len(f.outlines[0].rings[0]) == 20


def test_the_pole_edge_is_snapped_to_the_antimeridian(tmp_path):
    # Natural Earth's Arctic Ocean closes along the pole from -180 to 179.9999, which the pack
    # writer would refuse as an edge crossing the antimeridian
    ring = np.array([(-180.0, 71.0), (-180.0, 89.99999), (179.9999, 89.99999), (179.9999, 71.0), (0.0, 75.0)])
    f = ws.polygon_feature([ring[::-1]], tolerance_m=0, fid="arctic")
    lons = sorted({lon for _, lon in f.outlines[0].rings[0]})
    assert lons[0] == -180.0 and lons[-1] == 180.0
    layer = LayerData("marine", "polygon", {"id": ["arctic"], "name": ["Arctic"]}, ("x",), features=[f])
    write_pack(tmp_path, "t", "2026.11", [layer])  # no edge crosses the antimeridian any more


def test_line_feature_is_a_zero_area_ring_whose_boundary_is_the_line(tmp_path):
    line = np.array([(80.0, 25.0), (80.1, 25.0), (80.2, 25.1)])
    f = ws.line_feature([line], fid="river:1")
    ring = f.outlines[0].rings[0]
    assert ring == ((25.0, 80.0), (25.0, 80.1), (25.1, 80.2), (25.0, 80.1))  # out and back
    layer = LayerData("rivers", "polygon", {"id": ["river:1"], "name": ["R"]}, ("x",), features=[f])
    write_pack(tmp_path, "t", "2026.11", [layer])
    rivers = open_pack(tmp_path / "t-2026.11")["rivers"]
    assert rivers.query(25.0, 80.05) == -1  # nothing is ever inside a line
    _q, feat, km = rivers.near_boundary([25.01], [80.05], 5.0)
    assert feat.tolist() == [0] and km[0] == pytest.approx(1.112, abs=0.01)  # 0.01° of latitude


def test_line_feature_splits_at_the_antimeridian_and_drops_single_points():
    line = np.array([(179.5, 65.0), (179.9, 65.1), (-179.9, 65.2), (-179.5, 65.3)])
    f = ws.line_feature([line, np.array([(1.0, 1.0)])], fid="r")
    assert len(f.outlines) == 2  # one part each side of ±180; the one-point part is gone
    assert all(abs(lon) < 180 for o in f.outlines for r in o.rings for _, lon in r)


def test_area_is_on_the_sphere():
    one_degree = ws.polygon_feature([_square(0.0, 0.0, 1.0, n=2)], tolerance_m=0, fid="x")
    assert ws.area_km2(one_degree) == pytest.approx(12_364, rel=0.002)  # 1° x 1° at the equator
