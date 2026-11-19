"""packbuild.water: the world-water pack from Natural Earth, HydroLAKES and Wikidata, offline."""

import json
import zipfile
from pathlib import Path

import pytest
from gdw_kit import RESERVOIRS
from gdw_kit import write_archive as write_gdw
from hydrolakes_kit import opener_for, write_archive
from ne_water_kit import LAKE_FIELDS, MARINE_FIELDS, RIVER_FIELDS, box, write_lines, write_polygons

from packbuild import water
from packbuild.sources import url
from placewise.constants import water as const
from placewise.packs import open_pack


def _zip(folder, stem, shp):
    archive = folder / f"{stem}.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for ext in (".shp", ".shx", ".dbf"):
            z.write(shp.with_suffix(ext), f"{stem}{ext}")
    return archive


@pytest.fixture
def offline(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    ocean = {"name": "North Atlantic Ocean", "featurecla": "ocean", "wikidataid": "Q97", "ne_id": "1"}
    marine = write_polygons(src / "m", MARINE_FIELDS, [([box(-60, -80, 60, 0)], ocean)])
    ontario = {"name": "Lake Ontario", "featurecla": "Lake", "wikidataid": "Q1062", "ne_id": "11"}
    small = {"name": "Lake Small", "featurecla": "Lake", "ne_id": "21"}
    lakes = write_polygons(
        src / "l",
        LAKE_FIELDS,
        [([box(43.25, -79.7, 44.15, -76.2)], ontario), ([box(46.0, -84.0, 46.2, -83.8)], small)],
    )
    empty = write_polygons(src / "e", LAKE_FIELDS, [])
    ganges = {"name": "Ganges", "featurecla": "River", "wikidataid": "Q5089", "ne_id": "31"}
    rivers = write_lines(src / "r", RIVER_FIELDS, [([[(82.9, 25.2), (83.0, 25.3)]], ganges)])
    no_rivers = write_lines(src / "nr", RIVER_FIELDS, [])
    shps = {"marine": marine, "lakes": lakes, "lakes_north_america": empty, "lakes_europe": empty,
            "rivers": rivers, "rivers_north_america": no_rivers, "rivers_europe": no_rivers}  # fmt: skip
    files = {}
    for key, shp in shps.items():
        link = url("naturalearth-physical", key)
        files[link] = _zip(src, Path(link).stem, shp)
    sparql = src / "sparql.json"
    sparql.write_text(json.dumps({"results": {"bindings": [
        {"item": {"value": "http://www.wikidata.org/entity/Q325391"}, "label": {"value": "Dal Lake"},
         "coord": {"value": "Point(74.87 34.12)"}},
    ]}}))  # fmt: skip
    for q in water.WIKIDATA_QUERIES:
        files[url("wikidata", q)] = sparql
    covered = (
        5,
        "Ontario Pool",
        "Moses-Saunders",
        "",
        "",
        500.0,
        (43.4, -79.5, 44.0, -76.5),
    )  # in Lake Ontario
    files[url("gdw", "reservoirs")] = write_gdw(src, [*RESERVOIRS, covered])
    requested = []

    def fake_fetch(link, cache_dir, refresh=False, timeout=60):
        requested.append(link)
        return files[link]

    monkeypatch.setattr(water, "fetch", fake_fetch)
    (tmp_path / "remote").mkdir()
    archive = write_archive(tmp_path / "remote")
    return requested, opener_for(archive, url=url("hydrolakes", "polygons"))


def test_build_writes_the_four_layers(tmp_path, offline):
    requested, opener = offline
    path = water.build_water(tmp_path / "cache", tmp_path / "out", "2026.11", opener=opener)
    assert path == tmp_path / "out" / "world-water-2026.11"
    pack = open_pack(path)
    assert [layer.name for layer in pack] == ["marine", "lakes", "reservoirs", "rivers"]
    assert pack.name == const.PACK
    lakes = pack["lakes"]
    names = lakes.column("name").tolist()
    # HydroLAKES outlines named by Natural Earth (Ontario) and Wikidata (Dal Lake); Tahoe by its own
    # name; Natural Earth's uncovered Lake Small kept; the unnamed outline left out
    assert sorted(names) == ["Dal Lake", "Lake Ontario", "Lake Small", "Lake Tahoe"]
    assert lakes.sources == ("hydrolakes", "naturalearth-physical", "wikidata")
    assert pack["marine"].column("name").tolist() == ["North Atlantic Ocean"]
    tahoe = pack.names.exact("Lake Tahoe")
    assert [pack.names.layers[x] for x in tahoe.layer] == ["lakes"]
    assert pack["rivers"].column("id").tolist() == ["wikidata:Q5089"]
    assert set(pack.sources) == {"naturalearth-physical", "hydrolakes", "wikidata", "gdw"}
    assert all(link.startswith("https://") for link in requested)


def test_reservoirs_no_named_lake_covers_join_as_their_own_layer(tmp_path, offline):
    _, opener = offline
    pack = open_pack(water.build_water(tmp_path / "cache", tmp_path / "out", "2026.11", opener=opener))
    reservoirs = pack["reservoirs"]
    # the pool inside Lake Ontario is left out (the lake answers there); Lake Tahoe is a lake (a
    # control dam); Hirakud's HydroLAKES outline is unnamed here, so the reservoir stays
    assert reservoirs.column("name").tolist() == [
        "Big Meadows Reservoir", "Tehri Reservoir", "Nagarjuna Sagar", "Hirakud Reservoir",
    ]  # fmt: skip
    assert set(reservoirs.column("type").tolist()) == {"reservoir"} and reservoirs.sources == ("gdw",)
    tehri = pack.names.exact("Tehri Reservoir")
    assert [pack.names.layers[x] for x in tehri.layer] == ["reservoirs"]
    assert (tmp_path / "cache" / "gdw" / "GDW_reservoirs_v1_0.shp").exists()


def test_reservoirs_can_be_left_out(tmp_path, offline):
    requested, opener = offline
    layers = water.build_layers(tmp_path / "cache", with_reservoirs=False, opener=opener)
    assert [layer.name for layer in layers] == ["marine", "lakes", "rivers"]
    assert url("gdw", "reservoirs") not in requested


def test_without_hydrolakes_the_lakes_are_natural_earths(tmp_path, offline):
    requested, opener = offline
    layers = water.build_layers(tmp_path / "cache", with_hydrolakes=False, opener=opener)
    lakes = layers[1]
    assert lakes.columns["name"] == ["Lake Small", "Lake Ontario"]
    assert "Hirakud Reservoir" in layers[2].columns["name"]  # no lake covers it now
    assert not any("wikidata" in link for link in requested)
