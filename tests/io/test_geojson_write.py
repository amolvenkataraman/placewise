"""GeoJSON out: Outlines and Entities as RFC 7946 geometries and Features (placewise.io.geojson).
Shapes in the open equatorial Pacific, nothing real."""

import json

import numpy as np
import pytest

from placewise.geo import shapes
from placewise.io import entity_feature, outline_geometry, read_geojson, to_geojson, write_geojson
from placewise.model import BBox, Entity, Feature, Outline, Place, PlaceKind, Point

W = -150.0
# (lat, lon) rings, as packs hold them: clockwise outer on a map, counter-clockwise hole
OUTER = ((0.0, W), (1.0, W), (1.0, W + 1), (0.0, W + 1))
HOLE = ((0.4, W + 0.4), (0.4, W + 0.6), (0.6, W + 0.6), (0.6, W + 0.4))
ISLAND = ((0.45, W + 0.45), (0.55, W + 0.45), (0.55, W + 0.55), (0.45, W + 0.55))  # in the hole
APART = ((3.0, W), (3.0, W + 1), (4.0, W + 1), (4.0, W))


def _area(ring):  # GeoJSON (lon, lat) ring -> shoelace area, positive counter-clockwise
    return shapes.planar_signed_area([(lat, lon) for lon, lat in ring])


def test_a_polygon_with_a_hole_is_lon_lat_closed_and_wound_per_rfc_7946():
    g = outline_geometry(Outline((OUTER, HOLE)))
    assert g["type"] == "Polygon" and len(g["coordinates"]) == 2
    outer, hole = g["coordinates"]
    assert outer[0] == outer[-1] and hole[0] == hole[-1]
    assert {tuple(p) for p in outer} == {(W, 0.0), (W, 1.0), (W + 1, 1.0), (W + 1, 0.0)}  # (lon, lat)
    assert _area(outer) > 0 > _area(hole)  # outer counter-clockwise, hole clockwise


def test_rings_of_several_polygons_make_a_multipolygon_with_holes_in_place():
    g = outline_geometry(Outline((APART, HOLE, OUTER, ISLAND)))
    assert g["type"] == "MultiPolygon"
    assert [len(p) for p in g["coordinates"]] == [1, 2, 1]  # APART, OUTER with its hole, ISLAND
    (back,) = read_geojson(g)
    original = Outline((APART, HOLE, OUTER, ISLAND))
    lat, lon = np.meshgrid(np.linspace(-0.5, 4.5, 41), np.linspace(W - 0.5, W + 1.5, 17))
    assert (back.contains(lat.ravel(), lon.ravel()) == original.contains(lat.ravel(), lon.ravel())).all()


def test_simplify_drops_vertices_along_edges_and_rings_smaller_than_the_tolerance():
    dense = [(0.0, W + i / 50) for i in range(50)] + [(1.0, W + 1), (1.0, W)]
    tiny = ((0.5, W + 0.5), (0.5, W + 0.50001), (0.50001, W + 0.50001), (0.50001, W + 0.5))
    plain = outline_geometry(Outline((tuple(dense), tiny)))
    simple = outline_geometry(Outline((tuple(dense), tiny)), simplify_m=50)
    assert len(plain["coordinates"]) == 2 and len(plain["coordinates"][0]) == 53
    assert simple["type"] == "Polygon" and len(simple["coordinates"]) == 1  # the 1 m hole is gone
    assert len(simple["coordinates"][0]) == 5  # four corners, closed


def test_simplify_never_drops_everything():
    tiny = ((0.5, W + 0.5), (0.5, W + 0.50001), (0.50001, W + 0.50001), (0.50001, W + 0.5))
    g = outline_geometry(Outline((tiny,)), simplify_m=1000)
    assert g["type"] == "Polygon" and len(g["coordinates"][0]) == 5


def test_outline_to_geojson_is_the_same():
    o = Outline((OUTER, HOLE))
    assert o.to_geojson() == outline_geometry(o)
    assert o.to_geojson(simplify_m=10) == outline_geometry(o, 10)


def _entity(outline=None):
    place = Place("test:1", "Test Atoll", PlaceKind.PARK, point=Point(0.2, W + 0.2), tier=1,
                  codes={"iso2": "XA"})  # fmt: skip
    return Entity(place=place, point=place.point, bbox=BBox(0.0, W, 1.0, W + 1), radius_km=80.0,
                  outline=outline, region="North Province", country="XA")  # fmt: skip


def test_an_entity_is_a_feature_with_its_outline_or_its_point():
    f = entity_feature(_entity(Outline((OUTER, HOLE))))
    assert f["type"] == "Feature" and f["id"] == "test:1"
    assert f["bbox"] == [W, 0.0, W + 1, 1.0]
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"] == {
        "name": "Test Atoll", "kind": "park", "tier": 1, "iso2": "XA",
        "region": "North Province", "country": "XA",
    }  # fmt: skip
    point = _entity().geojson()
    assert point["geometry"] == {"type": "Point", "coordinates": [W + 0.2, 0.2]}
    assert _entity(Outline((OUTER,))).geojson(simplify_m=5) == entity_feature(_entity(Outline((OUTER,))), 5)


def test_a_collection_of_entities_outlines_and_features_written_to_a_file(tmp_path):
    feature = Feature((Outline((OUTER,)), Outline((APART,))), {"name": "two"}, "f1")
    items = [_entity(), Outline((OUTER, HOLE)), feature]
    path = write_geojson(items, tmp_path / "out.geojson")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == to_geojson(items)
    assert [f["geometry"]["type"] for f in data["features"]] == ["Point", "Polygon", "MultiPolygon"]
    assert data["features"][2]["id"] == "f1" and data["features"][2]["properties"] == {"name": "two"}
    with pytest.raises(TypeError):
        to_geojson([Point(0, 0)])
