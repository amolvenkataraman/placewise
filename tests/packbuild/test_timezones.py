"""packbuild.timezones: the curated zone tables checked and drawn as the packs' `timezones` layers.

Synthetic units in open Pacific water (lookup_kit's Alphaland and Betaland); zone names are real
IANA zones because the build checks them against the tz database.
"""

import json

import pytest
from datasets_kit import needs_datasets
from timezones_kit import box, polygon_layer

from packbuild import timezones

SOURCES = {
    "tzdb": {"title": "tz database", "url": "https://data.iana.org/time-zones/", "licence": "public domain"}
}


def world_doc(**changes):
    doc = {
        "tzdb": "2026f",
        "sources": SOURCES,
        "countries": {
            "iso:XA": {
                "admin1": {"iso:XA-N": "Europe/Paris", "iso:XA-S": ["Europe/Madrid", "Atlantic/Canary"]},
                "sources": ["tzdb"],
            },
            "iso:XB": "Asia/Tokyo",
            "ne:XC": {"zone": None, "sources": ["tzdb"], "notes": "uninhabited"},
            "iso:XD": {
                "zone": "Europe/Lisbon",
                "admin1": {"iso:XD-I": "Atlantic/Azores"},
                "sources": ["tzdb"],
            },
        },
        "shapes": [
            {
                "id": "tz:north-tip",
                "name": "North tip",
                "zone": "Pacific/Fiji",
                "within": "iso:XA-N",
                "boxes": [[0.9, -140.0, 1.0, -139.9]],
                "sources": ["tzdb"],
            }
        ],
    }
    doc.update(changes)
    return doc


def world_layers():
    countries = polygon_layer(
        "countries",
        [
            ("iso:XA", "Alphaland", {"adm0_a3": "XAA"}, box(0, -140, 1, -139)),
            ("iso:XB", "Betaland", {"adm0_a3": "XBB"}, box(0, -139, 1, -138)),
            ("ne:XC", "Gamma Rock", {"adm0_a3": "XCC"}, box(2, -140, 2.5, -139.5)),
            ("iso:XD", "Deltaland", {"adm0_a3": "XDD"}, box(3, -140, 4, -139)),
        ],
    )
    admin1 = polygon_layer(
        "admin1",
        [
            ("iso:XA-N", "North Province", {"adm0_a3": "XAA"}, box(0.5, -140, 1, -139)),
            ("iso:XA-S", "South Province", {"adm0_a3": "XAA"}, box(0, -140, 0.5, -139)),
            ("iso:XB-W", "West Region", {"adm0_a3": "XBB"}, box(0, -139, 1, -138)),
            ("iso:XD-M", "Mainland", {"adm0_a3": "XDD"}, box(3, -140, 4, -139.5)),
            ("iso:XD-I", "Islands", {"adm0_a3": "XDD"}, box(3, -139.5, 4, -139)),
        ],
    )
    return countries, admin1


def rows(layer):
    return [
        dict(zip(layer.columns, values, strict=True)) for values in zip(*layer.columns.values(), strict=True)
    ]


# --- the world layer ----------------------------------------------------------------------------


def test_world_layer_draws_shapes_then_admin1_units_then_whole_countries():
    countries, admin1 = world_layers()
    layer = timezones.world_layer(world_doc(), countries, admin1)
    assert layer.name == "timezones" and layer.kind == "polygon"
    assert layer.sources == ("placewise-timezones", "naturalearth")
    got = [
        (r["id"], r["zone"], r["zones"], r["basis"], r["unit"], r["within"], r["country"])
        for r in rows(layer)
    ]
    assert got == [
        ("tz:north-tip", "Pacific/Fiji", "", "shape", "", "iso:XA-N", "iso:XA"),
        ("tz:iso:XA-N", "Europe/Paris", "", "admin1", "iso:XA-N", "", "iso:XA"),
        ("tz:iso:XA-S", "Europe/Madrid", "Europe/Madrid|Atlantic/Canary", "admin1", "iso:XA-S", "", "iso:XA"),
        ("tz:iso:XD-I", "Atlantic/Azores", "", "admin1", "iso:XD-I", "", "iso:XD"),
        ("tz:iso:XB", "Asia/Tokyo", "", "country", "iso:XB", "", "iso:XB"),
        ("tz:ne:XC", "", "", "country", "ne:XC", "", "ne:XC"),  # no zone: the nearest-city rule answers
        ("tz:iso:XD", "Europe/Lisbon", "", "country", "iso:XD", "", "iso:XD"),
    ]
    assert [r["name"] for r in rows(layer)][:3] == ["North tip", "North Province", "South Province"]
    assert set(layer.columns) == set(layer.types)
    # each unit keeps its own outline; a shape is its boxes
    by_id = dict(zip(layer.columns["id"], layer.features, strict=True))
    assert by_id["tz:iso:XB"].outlines == countries.features[1].outlines
    assert by_id["tz:iso:XA-N"].outlines == admin1.features[0].outlines
    (ring,) = by_id["tz:north-tip"].outlines[0].rings
    assert sorted(set(ring)) == [(0.9, -140.0), (0.9, -139.9), (1.0, -140.0), (1.0, -139.9)]


def test_a_shape_can_be_a_polygon_or_several_boxes():
    doc = world_doc(
        shapes=[
            {
                "id": "tz:tri",
                "zone": "Pacific/Fiji",
                "within": "iso:XA",
                "polygon": [[0, -140], [1, -140], [0, -139]],
            },
            {
                "id": "tz:two",
                "zone": "Pacific/Fiji",
                "within": "iso:XB",
                "boxes": [[0, -139, 0.1, -138.9], [0.9, -138.1, 1, -138]],
            },
        ]
    )
    layer = timezones.world_layer(doc, *world_layers())
    tri, two = layer.features[:2]
    assert tri.outlines[0].rings == (((0.0, -140.0), (1.0, -140.0), (0.0, -139.0)),)
    assert len(two.outlines) == 2
    assert layer.columns["country"][:2] == ["iso:XA", "iso:XB"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d["countries"].update({"iso:XB": "Mars/Olympus"}), "iso:XB: unknown zone 'Mars/Olympus'"),
        (lambda d: d["countries"].pop("iso:XB"), "iso:XB: no entry"),
        (
            lambda d: d["countries"].update({"iso:ZZ": "Asia/Tokyo"}),
            "iso:ZZ: not a unit of the countries layer",
        ),
        (
            lambda d: d["countries"]["iso:XA"]["admin1"].update({"iso:XB-W": "Asia/Tokyo"}),
            "iso:XA: iso:XB-W is not one of its admin1 units",
        ),
        (lambda d: d["countries"]["iso:XA"]["admin1"].pop("iso:XA-S"), "iso:XA: no zone for iso:XA-S"),
        (lambda d: d["countries"]["iso:XA"].update({"sources": ["nope"]}), "iso:XA: unknown source 'nope'"),
        (lambda d: d["countries"]["iso:XA"].update({"colour": "red"}), "iso:XA: unknown keys colour"),
        (
            lambda d: d["countries"]["iso:XA"]["admin1"].update({"iso:XA-S": []}),
            "iso:XA-S: an empty list of zones",
        ),
        (
            lambda d: d["countries"]["iso:XA"]["admin1"].update({"iso:XA-S": ["Asia/Tokyo", "Asia/Tokyo"]}),
            "iso:XA-S: a zone listed twice",
        ),
        (
            lambda d: d["shapes"][0].update({"within": "iso:QQ-1"}),
            "tz:north-tip: within 'iso:QQ-1' is no unit",
        ),
        (lambda d: d["shapes"][0].update({"boxes": [[1, -140, 0.9, -139.9]]}), "tz:north-tip: bad box"),
        (lambda d: d["shapes"][0].update({"id": "north-tip"}), "north-tip: shape ids start with 'tz:'"),
        (lambda d: d["shapes"].append(dict(d["shapes"][0])), "tz:north-tip: listed twice"),
        (lambda d: d["shapes"][0].pop("boxes"), "tz:north-tip: needs boxes or a polygon"),
    ],
)
def test_every_problem_in_the_table_fails_the_build_and_names_the_entry(change, problem):
    doc = json.loads(json.dumps(world_doc()))
    change(doc)
    with pytest.raises(ValueError, match="datasets/timezones") as err:
        timezones.world_layer(doc, *world_layers())
    assert problem in str(err.value)


def test_problems_are_listed_together():
    doc = world_doc()
    doc["countries"]["iso:XB"] = "Mars/Olympus"
    doc["countries"].pop("iso:XD")
    with pytest.raises(ValueError) as err:
        timezones.world_layer(doc, *world_layers())
    assert "Mars/Olympus" in str(err.value) and "iso:XD: no entry" in str(err.value)


# --- country packs ------------------------------------------------------------------------------


def country_doc(**changes):
    doc = {
        "country": "US",
        "tzdb": "2026f",
        "sources": SOURCES,
        "admin1": {
            "iso:US-NV": {
                "zone": "America/Los_Angeles",
                "parts": {"census:32007": ["America/Los_Angeles", "America/Denver"]},
                "sources": ["tzdb"],
            },
            "iso:US-AZ": "America/Phoenix",
        },
        "shapes": [
            {"id": "tz:navajo-nation", "zone": "America/Denver", "aiannh": "2430"},
            {"id": "tz:corner", "zone": "America/Denver", "boxes": [[36.9, -110.0, 37.0, -109.9]]},
        ],
    }
    doc.update(changes)
    return doc


def country_layers():
    states = polygon_layer(
        "states",
        [
            ("iso:US-NV", "Nevada", {"statefp": "32"}, box(35, -120, 42, -114)),
            ("iso:US-AZ", "Arizona", {"statefp": "04"}, box(31, -114, 37, -109)),
        ],
    )
    counties = polygon_layer(
        "counties",
        [
            ("census:32007", "Elko County", {"statefp": "32"}, box(39.5, -117, 42, -114)),
            ("census:04001", "Apache County", {"statefp": "04"}, box(33.5, -110, 37, -109)),
        ],
    )
    return states, counties


def parent(layer, field="statefp"):
    by_code = dict(zip(layer.columns[field], layer.columns["id"], strict=True))
    return lambda part, row: by_code[row[field]]


def test_country_layer_draws_shapes_then_parts_then_admin1_units():
    states, counties = country_layers()
    navajo = box(35.5, -111.5, 37, -109)
    layer = timezones.country_layer(
        country_doc(),
        states,
        [counties],
        parent(states),
        {"tz:navajo-nation": navajo},
        sources=("uscensus",),
    )
    assert layer.sources == ("placewise-timezones", "uscensus")
    got = [(r["id"], r["zone"], r["zones"], r["basis"], r["unit"], r["country"]) for r in rows(layer)]
    assert got == [
        ("tz:navajo-nation", "America/Denver", "", "shape", "", "iso:US"),
        ("tz:corner", "America/Denver", "", "shape", "", "iso:US"),
        (
            "tz:census:32007",
            "America/Los_Angeles",
            "America/Los_Angeles|America/Denver",
            "part",
            "census:32007",
            "iso:US",
        ),
        ("tz:iso:US-NV", "America/Los_Angeles", "", "admin1", "iso:US-NV", "iso:US"),
        ("tz:iso:US-AZ", "America/Phoenix", "", "admin1", "iso:US-AZ", "iso:US"),
    ]
    assert layer.features[0].outlines == navajo.outlines


def test_finer_parts_come_before_the_parts_they_lie_in():
    provinces = polygon_layer(
        "provinces", [("statcan:47", "Saskatchewan", {"pruid": "47"}, box(49, -110, 60, -102))]
    )
    cd = polygon_layer("cd", [("statcan:4717", "Division No. 17", {"pruid": "47"}, box(53, -110, 54, -108))])
    csd = polygon_layer(
        "csd", [("statcan:4717029", "Lloydminster (Part)", {"pruid": "47"}, box(53.2, -110, 53.4, -109.9))]
    )
    doc = {
        "country": "CA",
        "sources": SOURCES,
        "admin1": {
            "statcan:47": {
                "zone": "America/Regina",
                "parts": {"statcan:4717": "America/Swift_Current", "statcan:4717029": "America/Edmonton"},
            }
        },
        "shapes": [],
    }
    layer = timezones.country_layer(doc, provinces, [cd, csd], parent(provinces, "pruid"), {}, ("statcan",))
    assert layer.columns["id"] == ["tz:statcan:4717029", "tz:statcan:4717", "tz:statcan:47"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d["admin1"].pop("iso:US-AZ"), "iso:US-AZ: no entry"),
        (
            lambda d: d["admin1"].update({"iso:US-ZZ": "America/Denver"}),
            "iso:US-ZZ: not a unit of the states layer",
        ),
        (
            lambda d: d["admin1"]["iso:US-NV"]["parts"].update({"census:04001": "America/Denver"}),
            "iso:US-NV: census:04001 lies in iso:US-AZ",
        ),
        (
            lambda d: d["admin1"]["iso:US-NV"]["parts"].update({"census:99999": "America/Denver"}),
            "iso:US-NV: census:99999 is not a unit of the pack",
        ),
        (lambda d: d["admin1"]["iso:US-NV"].pop("zone"), "iso:US-NV: needs a zone"),
        (lambda d: d["shapes"][0].update({"aiannh": "9999"}), "tz:navajo-nation: no geometry"),
        (lambda d: d.update({"country": "CA"}), "admin1 units are of US"),
    ],
)
def test_every_problem_in_a_country_table_fails_the_build(change, problem):
    doc = json.loads(json.dumps(country_doc()))
    change(doc)
    states, counties = country_layers()
    shapes = {"tz:navajo-nation": box(35.5, -111.5, 37, -109)} if doc["shapes"][0]["aiannh"] == "2430" else {}
    with pytest.raises(ValueError, match="datasets/timezones") as err:
        timezones.country_layer(doc, states, [counties], parent(states), shapes, ("uscensus",))
    assert problem in str(err.value)


# --- the dataset files -------------------------------------------------------------------------


def test_load_reads_one_table_from_the_datasets_folder(tmp_path, monkeypatch):
    (tmp_path / "timezones").mkdir()
    (tmp_path / "timezones" / "world.json").write_text(json.dumps(world_doc()), encoding="utf-8")
    monkeypatch.setenv("PACKBUILD_DATASETS", str(tmp_path))
    assert timezones.load("world")["countries"]["iso:XB"] == "Asia/Tokyo"
    with pytest.raises(FileNotFoundError, match=r"usa\.json"):
        timezones.load("usa")


def test_aiannh_codes_lists_the_areas_a_table_draws():
    assert timezones.aiannh_codes(country_doc()) == {"tz:navajo-nation": "2430"}


@needs_datasets
@pytest.mark.parametrize("name", ["world", "usa", "can"])
def test_the_curated_tables_name_only_real_zones_and_sources(name):
    doc = timezones.load(name)
    assert timezones.check_entries(doc) == []
    assert doc["tzdb"]


@needs_datasets
def test_the_us_table_draws_the_navajo_nation_and_annette_island_from_census_areas():
    assert timezones.aiannh_codes(timezones.load("usa")) == {
        "tz:navajo-nation": "2430",
        "tz:annette-island": "0110",
    }
