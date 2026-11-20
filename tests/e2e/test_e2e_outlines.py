"""Outlines as GeoJSON on the world pack (placewise.outline, Entity.geojson): parts, holes and
simplification on public places only."""

import pytest
from e2e_kit import geocoder, require_packs

from placewise.io import read_geojson


@pytest.fixture(scope="module")
def geo():
    require_packs("world")
    return geocoder("world")


def _vertices(g):
    polygons = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    return sum(len(ring) for polygon in polygons for ring in polygon)


def test_lesotho_is_a_hole_in_south_africa(geo):
    g = geo.outline("iso:ZA")
    assert g["type"] == "MultiPolygon"  # the mainland and the Prince Edward Islands
    assert any(len(polygon) == 2 for polygon in g["coordinates"])  # the mainland with Lesotho's hole
    (za,) = read_geojson(g)
    assert za.contains(-26.2041, 28.0473) and not za.contains(-29.3100, 27.4800)  # Johannesburg, Maseru


def test_italy_has_holes_for_the_vatican_and_san_marino(geo):
    (it,) = read_geojson(geo.outline("iso:IT"))
    assert it.contains(41.8933, 12.4829)  # Rome
    assert not it.contains(41.9029, 12.4534) and not it.contains(43.9424, 12.4578)


def test_simplify_drops_vertices_and_holes_smaller_than_the_tolerance(geo):
    full, simple = geo.outline("iso:US-CA"), geo.outline("iso:US-CA", simplify_m=500)
    assert full["type"] == simple["type"] == "MultiPolygon"  # the mainland and the Channel Islands
    assert _vertices(simple) < 0.5 * _vertices(full)
    (it,) = read_geojson(geo.outline("iso:IT", simplify_m=500))
    assert it.contains(41.9029, 12.4534)  # the Vatican (0.5 km²) is gone at 500 m


def test_entity_feature_carries_the_outline_and_the_place(geo):
    f = geo.get("iso:US-CA", geometry=True).geojson(simplify_m=1000)
    assert f["id"] == "iso:US-CA" and f["properties"]["name"] == "California"
    assert f["geometry"]["type"] == "MultiPolygon"
    west, south, east, north = f["bbox"]
    assert -125 < west < -124 and 32 < south < 33 and -115 < east < -114 and 41 < north < 42.1
