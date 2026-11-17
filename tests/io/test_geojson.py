import json

import pytest

from placewise.io import read_geojson

# GeoJSON is (lon, lat); placewise is (lat, lon)
COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "id": "square",
            "properties": {"name": "Square with hole"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                    [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Two islands"},
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[20, 0], [22, 0], [22, 2], [20, 2], [20, 0]]],
                    [[[30, 0], [32, 0], [32, 2], [30, 2], [30, 0]]],
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "A point"},
            "geometry": {"type": "Point", "coordinates": [1, 1]},
        },
    ],
}


def test_reads_polygons_multipolygons_and_skips_other_geometry():
    square, islands = read_geojson(COLLECTION)
    assert square.id == "square" and square.properties == {"name": "Square with hole"}
    assert square.outlines[0].rings[0][1] == (0.0, 10.0)  # [lon 10, lat 0] becomes (lat 0, lon 10)
    assert square.contains(2, 2) and not square.contains(5, 5)  # the hole
    assert len(islands.outlines) == 2
    assert islands.contains(1, 21) and islands.contains(1, 31) and not islands.contains(1, 25)


def test_reads_files_and_bare_geometries(tmp_path):
    path = tmp_path / "zones.geojson"
    path.write_text(json.dumps(COLLECTION))
    assert len(read_geojson(path)) == 2
    (bare,) = read_geojson(COLLECTION["features"][0]["geometry"])
    assert bare.id is None and bare.contains(2, 2)


def test_rejects_non_geojson():
    with pytest.raises(ValueError):
        read_geojson({"type": "Banana"})
