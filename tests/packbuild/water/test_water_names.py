"""packbuild.sources.water.names: HydroLAKES outlines named from Natural Earth and Wikidata."""

import json

import pytest

from packbuild.sources.water import names
from placewise.model import Feature, Outline
from placewise.packs import LayerData


def _box(south, west, north, east, fid):
    return Feature((Outline((((south, west), (south, east), (north, east), (north, west)),)),), id=fid)


def _layer(rows, source):
    """rows: (id, name, type, wikidata, area, box)"""
    columns = {
        "id": [r[0] for r in rows], "name": [r[1] for r in rows], "type": [r[2] for r in rows],
        "wikidata": [r[3] for r in rows], "aliases": [""] * len(rows), "source": [source] * len(rows),
        "area_km2": [r[4] for r in rows],
    }  # fmt: skip
    features = [_box(*r[5], r[0]) for r in rows]
    return LayerData("lakes", "polygon", columns, (source,), features=features)


HL = [
    ("hydrolakes:1", "Lake Ontario", "lake", "", 19347.0, (43.2, -79.8, 44.2, -76.1)),
    ("hydrolakes:2", "", "reservoir", "", 500.8, (20.5, 83.5, 21.8, 84.0)),
    ("hydrolakes:4", "", "lake", "", 11.7, (34.08, 74.84, 34.14, 74.89)),
    ("hydrolakes:5", "", "lake", "", 10.5, (10.0, 10.0, 10.03, 10.03)),
    ("hydrolakes:8", "", "lake", "", 12.0, (60.0, 10.0, 60.05, 10.05)),
]
NE = [
    ("wikidata:Q1062", "Lake Ontario", "lake", "Q1062", 18900.0, (43.25, -79.7, 44.15, -76.2)),
    ("ne:7", "Whitefish Bay", "lake", "", 300.0, (43.3, -79.0, 43.5, -78.8)),  # drawn inside Ontario
    ("ne:12", "Hirakud Reservoir", "reservoir", "", 700.0, (20.45, 83.45, 21.85, 84.05)),
    ("ne:21", "Lake Small", "lake", "", 40.0, (46.0, -84.0, 46.2, -83.8)),  # no HydroLAKES outline
]


def _wikidata(tmp_path, rows):
    bindings = [
        {"item": {"value": f"http://www.wikidata.org/entity/{q}"}, "label": {"value": label},
         "coord": {"value": f"Point({lon} {lat})"}}
        for q, label, lat, lon in rows
    ]  # fmt: skip
    path = tmp_path / "sparql"
    path.write_text(json.dumps({"results": {"bindings": bindings}}))
    return path


@pytest.fixture
def joined(tmp_path):
    points = names.wikidata_points([
        _wikidata(tmp_path, [
            ("Q325391", "Dal Lake", 34.12, 74.87),
            ("Q999999", "Dal Lake (east basin)", 34.13, 74.88),  # a second item: the older one wins
            ("Q1062", "Lake Ontario", 34.10, 74.85),  # already Natural Earth's: not given twice
            ("Q424242", "Nowhere Lake", 0.0, 0.0),  # in no outline
        ])
    ])  # fmt: skip
    return names.join(_layer(HL, "hydrolakes"), _layer(NE, "naturalearth"), points, tmp_path / "work")


def _rows(layer):
    return {i: {k: v[n] for k, v in layer.columns.items()} for n, i in enumerate(layer.columns["id"])}


def test_natural_earth_names_the_outline_it_covers(joined):
    rows = _rows(joined)
    ontario = rows["wikidata:Q1062"]  # the Wikidata id is the stable public id
    assert ontario["name"] == "Lake Ontario" and ontario["source"] == "hydrolakes"
    assert ontario["area_km2"] == 19347.0  # HydroLAKES' outline and area
    hirakud = next(r for r in rows.values() if r["name"] == "Hirakud Reservoir")
    assert hirakud["source"] == "hydrolakes" and hirakud["type"] == "reservoir"
    assert hirakud["id"] == "hydrolakes:2"


def test_covered_natural_earth_lakes_go_and_the_rest_stay(joined):
    by_name = {r["name"]: r for r in _rows(joined).values()}
    assert "Whitefish Bay" not in by_name  # inside HydroLAKES' Lake Ontario, which keeps its name
    assert by_name["Lake Small"]["source"] == "naturalearth"


def test_wikidata_names_unnamed_outlines(joined):
    by_name = {r["name"]: r for r in _rows(joined).values()}
    dal = by_name["Dal Lake"]
    assert dal["wikidata"] == "Q325391" and dal["id"] == "wikidata:Q325391"


def test_unnamed_outlines_are_left_out_and_rows_are_smallest_first(joined):
    assert set(joined.columns["name"]) == {"Lake Ontario", "Hirakud Reservoir", "Dal Lake", "Lake Small"}
    areas = joined.columns["area_km2"]
    assert areas == sorted(areas)
    assert joined.sources == ("hydrolakes", "naturalearth-physical", "wikidata")
    assert [f.id for f in joined.features] == joined.columns["id"]


def test_wikidata_points_parse_the_query_result(tmp_path):
    path = _wikidata(tmp_path, [("Q325391", "Dal Lake", 34.12, 74.87)])
    assert names.wikidata_points([path]) == [("Q325391", "Dal Lake", 34.12, 74.87)]
