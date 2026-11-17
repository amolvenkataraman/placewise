"""packbuild.sources.water.naturalearth: Natural Earth's marine polygons, lakes and rivers."""

import pytest
from ne_water_kit import (
    LAKE_FIELDS,
    MARINE_FIELDS,
    RIVER_FIELDS,
    box,
    write_lines,
    write_polygons,
)

from packbuild.sources.water import naturalearth as ne


def _col(layer, name):
    return list(layer.columns[name])


@pytest.fixture
def marine_shp(tmp_path):
    rows = [
        ([box(0, -60, 60, 0)], {"name": "North Atlantic Ocean", "name_en": "Atlantic Ocean",
                                "featurecla": "ocean", "wikidataid": "Q97", "ne_id": "1"}),
        ([box(-60, -60, 0, 0)], {"name": "South Atlantic Ocean", "name_en": "Atlantic Ocean",
                                 "featurecla": "ocean", "wikidataid": "Q97", "ne_id": "2"}),
        ([box(-60, 20, 0, 100)], {"name": "INDIAN OCEAN", "name_en": "Indian Ocean",
                                  "featurecla": "ocean", "wikidataid": "Q1239", "ne_id": "3"}),
        ([box(10, 60, 20, 70)], {"name": "Arabian Sea", "name_en": "Arabian Sea", "featurecla": "sea",
                                 "wikidataid": "Q35402", "ne_id": "4"}),
        ([box(18, -97, 22, -92)], {"name": "Bahía de Campeche", "name_en": "Bay of Campeche",
                                   "featurecla": "bay", "wikidataid": "Q61304", "ne_id": "5"}),
        ([box(24, 48, 30, 56)], {"name": "Persian Gulf", "name_en": "Persian Gulf", "featurecla": "gulf",
                                 "namealt": "Arabian Gulf", "wikidataid": "Q34675", "ne_id": "6"}),
        ([box(59, -153, 61, -150)], {"name": "Cook Inlet", "name_en": "Tikahtnu Inlet", "featurecla": "bay",
                                     "wikidataid": "Q1129590", "ne_id": "7"}),
        ([box(52, -130, 53, -129)], {"featurecla": "generic", "ne_id": "8"}),  # unnamed: left out
        # one reef drawn as two records with one ne_id: one feature
        ([box(-20, 145, -15, 147)], {"name": "Great Barrier Reef", "featurecla": "reef",
                                     "wikidataid": "Q7343", "ne_id": "9"}),
        ([box(-24, 150, -21, 152)], {"name": "Great Barrier Reef", "featurecla": "reef",
                                     "wikidataid": "Q7343", "ne_id": "9"}),
    ]  # fmt: skip
    return write_polygons(tmp_path / "ne_10m_geography_marine_polys", MARINE_FIELDS, rows)


def test_marine_names_are_english_with_the_ocean_halves_kept(marine_shp):
    layer = ne.marine(marine_shp)
    assert layer.name == "marine" and layer.kind == "polygon"
    assert layer.sources == ("naturalearth-physical",)
    names = set(_col(layer, "name"))
    # name_en drops the North/South split and capitals come title-cased
    assert {"North Atlantic Ocean", "South Atlantic Ocean", "Indian Ocean"} <= names
    assert "Bay of Campeche" in names  # the English form, not the Spanish
    assert "Cook Inlet" in names  # name_en's surprise "Tikahtnu Inlet" is not used
    assert len(names) == len(_col(layer, "name")) == 8  # unnamed out, the reef's two records one


def test_marine_ids_types_aliases_and_order(marine_shp):
    layer = ne.marine(marine_shp)
    row = {n: i for i, n in enumerate(_col(layer, "name"))}
    ids = _col(layer, "id")
    assert ids[row["Arabian Sea"]] == "wikidata:Q35402"
    assert ids[row["North Atlantic Ocean"]] == "ne:1"  # Q97 is both halves: not unique
    assert _col(layer, "wikidata")[row["North Atlantic Ocean"]] == "Q97"
    assert _col(layer, "type")[row["Persian Gulf"]] == "gulf"
    assert _col(layer, "aliases")[row["Persian Gulf"]] == "Arabian Gulf"
    assert _col(layer, "aliases")[row["Bay of Campeche"]] == "Bahía de Campeche"
    reef = layer.features[row["Great Barrier Reef"]]
    assert len(reef.outlines) == 2
    areas = _col(layer, "area_km2")
    assert areas == sorted(areas)  # smallest first: a bay inside a sea answers before the sea
    assert layer.types["area_km2"] == "f8"


@pytest.fixture
def lake_shps(tmp_path):
    world = [
        ([box(43.2, -79.8, 44.2, -76.1)], {"name": "Lake Ontario", "name_en": "Ontario", "featurecla": "Lake",
                                           "wikidataid": "Q1062", "ne_id": "11"}),
        ([box(20.5, 83.5, 21.8, 84.0)], {"name": "Hinakud Dam", "name_en": "Hirakud Dam",
                                         "featurecla": "Reservoir", "ne_id": "12"}),
        ([box(16.5, 79.0, 16.7, 79.3)], {"name": "Nagarjuna Sagar Dam", "featurecla": "Reservoir",
                                         "ne_id": "13"}),
        ([box(10, 10, 11, 11)], {"featurecla": "Lake", "ne_id": "14"}),  # unnamed: left out
        ([box(38.9, -120.2, 39.25, -119.9)], {"name": "LAKE TAHOE", "featurecla": "Lake",
                                              "wikidataid": "Q169962", "ne_id": "15"}),
    ]  # fmt: skip
    north_america = [
        ([box(46, -84, 46.2, -83.8)], {"name": "Lake Small", "featurecla": "Lake", "ne_id": "21"}),
    ]
    return [
        write_polygons(tmp_path / "ne_10m_lakes", LAKE_FIELDS, world),
        write_polygons(tmp_path / "ne_10m_lakes_north_america", LAKE_FIELDS, north_america),
    ]


def test_lakes_merge_the_files_keep_the_generic_and_fix_reservoir_names(lake_shps):
    layer = ne.lakes(lake_shps)
    assert layer.name == "lakes" and layer.sources == ("naturalearth-physical",)
    names = _col(layer, "name")
    assert set(names) == {"Lake Ontario", "Hirakud Reservoir", "Nagarjuna Sagar", "Lake Tahoe", "Lake Small"}
    row = {n: i for i, n in enumerate(names)}
    assert _col(layer, "type")[row["Hirakud Reservoir"]] == "reservoir"
    assert _col(layer, "type")[row["Lake Ontario"]] == "lake"
    assert _col(layer, "id")[row["Lake Ontario"]] == "wikidata:Q1062"
    assert _col(layer, "id")[row["Lake Small"]] == "ne:21"
    assert set(_col(layer, "source")) == {"naturalearth"}
    areas = _col(layer, "area_km2")
    assert areas == sorted(areas)
    assert areas[row["Lake Ontario"]] == pytest.approx(33_070, rel=0.01)  # the box, on the sphere


def test_rivers_join_segments_drop_lake_centerlines_and_name_in_english(tmp_path):
    rows = [
        ([[(82.9, 25.2), (83.0, 25.3)]], {"name": "Ganges", "name_en": "Ganges", "featurecla": "River",
                                          "wikidataid": "Q5089", "ne_id": "31", "scalerank": "1"}),
        ([[(83.0, 25.3), (83.1, 25.35)]], {"name": "Ganges", "name_en": "Ganges", "featurecla": "River",
                                           "wikidataid": "Q5089", "ne_id": "32", "scalerank": "1"}),
        ([[(105.0, 21.0), (105.2, 21.1)]], {"name": "Da", "name_en": "Black", "featurecla": "River",
                                            "wikidataid": "Q1922260", "ne_id": "33", "scalerank": "8"}),
        ([[(-76.0, 44.0), (-75.0, 44.5)]], {"name": "Lake Ontario", "featurecla": "Lake Centerline",
                                            "ne_id": "34"}),
        ([[(1.0, 1.0), (1.1, 1.1)]], {"featurecla": "River", "ne_id": "35"}),  # unnamed: left out
    ]  # fmt: skip
    na = [
        ([[(-88.0, 40.0), (-89.0, 41.0)]], {"name": "Illinois", "name_en": "Illinois", "featurecla": "River",
                                            "name_full": "Illinois River", "ne_id": "41", "scalerank": "**"}),
    ]  # fmt: skip
    layer = ne.rivers(
        [write_lines(tmp_path / "ne_10m_rivers_lake_centerlines", RIVER_FIELDS, rows),
         write_lines(tmp_path / "ne_10m_rivers_north_america", RIVER_FIELDS, na)]
    )  # fmt: skip
    assert layer.name == "rivers" and layer.kind == "polygon"
    names = _col(layer, "name")
    assert names == ["Ganges", "Black River", "Illinois River"]
    assert _col(layer, "id") == ["wikidata:Q5089", "wikidata:Q1922260", "ne:41"]
    assert len(layer.features[0].outlines) == 2  # the two Ganges segments are one river
    assert _col(layer, "type") == ["river"] * 3
    assert _col(layer, "scalerank") == [1, 8, -1]  # an overflowed number is null


def test_english_names():
    assert ne.english_lake_name("LAKE TAHOE", "reservoir") == "Lake Tahoe"
    assert ne.english_lake_name("Smith Mountain Lake", "reservoir") == "Smith Mountain Lake"
    assert ne.english_lake_name("Bhakra Dam", "reservoir") == "Bhakra Reservoir"
    assert ne.english_lake_name("Gobind Sagar Dam", "reservoir") == "Gobind Sagar"
    assert ne.english_lake_name("Banggong Co", "lake") == "Pangong Tso"  # the English name
    # rivers: Natural Earth's own English form when it has one; a translated name_en is bare
    assert ne.english_river_name("Ganges", "Ganges") == "Ganges"
    assert ne.english_river_name("Da", "Black") == "Black River"
    assert ne.english_river_name("Río Negro", "Negro") == "Negro River"
    assert ne.english_river_name("Río Negro", "") == "Río Negro"
    assert ne.english_river_name("Illinois", "Illinois", "Illinois River") == "Illinois River"
