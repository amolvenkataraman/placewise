"""packbuild.sources.water.names: HydroLAKES outlines named from Natural Earth and Wikidata."""

import json
import math

import pytest

from packbuild.sources.water import names
from placewise.model import Feature, Outline
from placewise.packs import LayerData


def _box(south, west, north, east, fid):
    return Feature((Outline((((south, west), (south, east), (north, east), (north, west)),)),), id=fid)


def _layer(rows, source, elevations=None):
    """rows: (id, name, type, wikidata, area, box); elevations: the elevation_m column, if any"""
    columns = {
        "id": [r[0] for r in rows], "name": [r[1] for r in rows], "type": [r[2] for r in rows],
        "wikidata": [r[3] for r in rows], "aliases": [""] * len(rows), "source": [source] * len(rows),
        "area_km2": [r[4] for r in rows],
    }  # fmt: skip
    if elevations is not None:
        columns["elevation_m"] = list(elevations)
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
    hl = _layer(HL, "hydrolakes", elevations=[75.0, 187.0, 1583.0, 0.0, 10.0])
    return names.join(hl, _layer(NE, "naturalearth"), points, tmp_path / "work")


def _rows(layer):
    return {i: {k: v[n] for k, v in layer.columns.items()} for n, i in enumerate(layer.columns["id"])}


def test_natural_earth_names_the_outline_it_covers(joined):
    rows = _rows(joined)
    ontario = rows["wikidata:Q1062"]  # the Wikidata id is the stable public id
    assert ontario["name"] == "Lake Ontario" and ontario["source"] == "hydrolakes"
    assert ontario["area_km2"] == 19347.0  # HydroLAKES' outline and area
    assert ontario["elevation_m"] == 75.0  # and surface elevation
    hirakud = next(r for r in rows.values() if r["name"] == "Hirakud Reservoir")
    assert hirakud["source"] == "hydrolakes" and hirakud["type"] == "reservoir"
    assert hirakud["id"] == "hydrolakes:2"


def test_covered_natural_earth_lakes_go_and_the_rest_stay(joined):
    by_name = {r["name"]: r for r in _rows(joined).values()}
    assert "Whitefish Bay" not in by_name  # inside HydroLAKES' Lake Ontario, which keeps its name
    assert by_name["Lake Small"]["source"] == "naturalearth"
    assert math.isnan(by_name["Lake Small"]["elevation_m"])  # Natural Earth gives none
    assert by_name["Dal Lake"]["elevation_m"] == 1583.0


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


def test_reservoirs_a_named_lake_covers_are_dropped(tmp_path):
    lakes = _layer(
        [
            ("wikidata:Q1", "Hirakud Reservoir", "reservoir", "Q1", 500.0, (20.5, 83.5, 21.8, 84.0)),
            ("wikidata:Q2", "Lake Edge", "lake", "Q2", 30.0, (30.0, 78.0, 30.1, 78.1)),
        ],
        "hydrolakes",
    )
    reservoirs = _layer(
        [
            ("gdw:1687", "Tehri Reservoir", "reservoir", "", 18.9, (30.35, 78.40, 30.45, 78.55)),  # no lake
            ("gdw:2", "Edge Reservoir", "reservoir", "", 40.0, (30.05, 78.05, 30.2, 78.2)),  # a ninth in one
            ("gdw:336", "Hirakud Reservoir", "reservoir", "", 499.5, (20.55, 83.55, 21.75, 83.95)),  # in it
        ],
        "gdw",
    )
    kept = names.drop_covered(reservoirs, lakes, tmp_path)
    assert kept.columns["id"] == ["gdw:1687", "gdw:2"]
    assert [f.id for f in kept.features] == ["gdw:1687", "gdw:2"]
    assert kept.name == "lakes" and kept.columns["area_km2"] == [18.9, 40.0]
    assert names.drop_covered(reservoirs, _layer([], "hydrolakes"), tmp_path).columns["id"] == [
        "gdw:1687", "gdw:2", "gdw:336",
    ]  # fmt: skip
