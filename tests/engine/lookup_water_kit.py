"""A synthetic world-water pack over lookup_kit's invented Pacific world (nothing real).

Test Ocean     lat -5 .. 5, lon -145 .. -135, with the land of Alphaland + Betaland and of
               Gammaland as holes, as Natural Earth's marine polygons follow the coast
Gamma Bay      lat 1.5 .. 2, lon -140 .. -139.5, drawn over the ocean (smaller: answers first)
Far Sea        lat -12 .. -8, lon -162 .. -158, far from every country
Lake Alpha     lat 0.3 .. 0.4, lon -139.9 .. -139.8, inside Alphaland (about 123 km²)
Alpha River    along lat 0.6 from lon -139.95 to -139.7
Southam Reservoir  lat 0.1 .. 0.15, lon -139.7 .. -139.6 (Global Dam Watch, about 62 km²)
Alpha Pool     lat 0.35 .. 0.45, lon -139.85 .. -139.75, a reservoir overlapping Lake Alpha
"""

from lookup_kit import CREATED, box_feature

from placewise.model import Feature, Outline
from placewise.packs import LayerData, write_pack


def _ring(south, west, north, east):
    return ((south, west), (south, east), (north, east), (north, west))


def marine_layer():
    ocean = Feature(
        (Outline((_ring(-5, -145, 5, -135), _ring(0, -140, 1, -138), _ring(2, -140, 2.5, -139.5))),),
        id="wikidata:Q90001",
    )
    rows = [
        # smallest first, as the build sorts them
        ("ne:2", "Gamma Bay", "bay", "", box_feature(1.5, -140, 2.0, -139.5, fid="ne:2")),
        ("ne:3", "Far Sea", "sea", "", box_feature(-12, -162, -8, -158, fid="ne:3")),
        ("wikidata:Q90001", "Test Ocean", "ocean", "Q90001", ocean),
    ]
    columns = {
        "id": [r[0] for r in rows],
        "name": [r[1] for r in rows],
        "type": [r[2] for r in rows],
        "wikidata": [r[3] for r in rows],
        "aliases": ["", "", "Testic Ocean"],
        "area_km2": [1.0, 2.0, 3.0],
    }
    return LayerData("marine", "polygon", columns, ("synthetic",), features=[r[4] for r in rows])


def lakes_layer(source="hydrolakes"):
    columns = {
        "id": ["hydrolakes:1"],
        "name": ["Lake Alpha"],
        "type": ["lake"],
        "wikidata": [""],
        "aliases": [""],
        "source": [source],
        "area_km2": [123.0],
    }
    features = [box_feature(0.3, -139.9, 0.4, -139.8, fid="hydrolakes:1")]
    return LayerData("lakes", "polygon", columns, ("synthetic",), features=features)


def reservoirs_layer():
    columns = {
        "id": ["gdw:2", "gdw:1"],
        "name": ["Southam Reservoir", "Alpha Pool"],
        "type": ["reservoir", "reservoir"],
        "wikidata": ["", ""],
        "aliases": ["", ""],
        "source": ["gdw", "gdw"],
        "area_km2": [62.0, 124.0],
    }
    features = [
        box_feature(0.1, -139.7, 0.15, -139.6, fid="gdw:2"),
        box_feature(0.35, -139.85, 0.45, -139.75, fid="gdw:1"),
    ]
    return LayerData("reservoirs", "polygon", columns, ("synthetic",), features=features)


def rivers_layer():
    line = [(0.6, -139.95), (0.6, -139.85), (0.6, -139.7)]
    ring = tuple(line + line[-2:0:-1])
    columns = {"id": ["wikidata:Q90002"], "name": ["Alpha River"], "type": ["river"], "wikidata": ["Q90002"]}
    features = [Feature((Outline((ring,)),), id="wikidata:Q90002")]
    return LayerData("rivers", "polygon", columns, ("synthetic",), features=features)


def write_water(out_dir, lake_source="hydrolakes", reservoirs=False):
    """The synthetic water pack, named like the real one: world-water-2026.11."""
    layers = [
        marine_layer(),
        lakes_layer(lake_source),
        *([reservoirs_layer()] if reservoirs else []),
        rivers_layer(),
    ]
    return write_pack(out_dir, "world-water", "2026.11", layers, created=CREATED)
