"""packbuild.water: the world-water pack from Natural Earth, HydroLAKES and Wikidata, offline."""

import json
import zipfile
from pathlib import Path

import pytest
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
    requested = []

    def fake_fetch(link, cache_dir, refresh=False, timeout=60):
        requested.append(link)
        return files[link]

    monkeypatch.setattr(water, "fetch", fake_fetch)
    (tmp_path / "remote").mkdir()
    archive = write_archive(tmp_path / "remote")
    return requested, opener_for(archive, url=url("hydrolakes", "polygons"))


def test_build_writes_the_three_layers(tmp_path, offline):
    requested, opener = offline
    path = water.build_water(tmp_path / "cache", tmp_path / "out", "2026.11", opener=opener)
    assert path == tmp_path / "out" / "world-water-2026.11"
    pack = open_pack(path)
    assert [layer.name for layer in pack] == ["marine", "lakes", "rivers"] and pack.name == const.PACK
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
    assert set(pack.sources) == {"naturalearth-physical", "hydrolakes", "wikidata"}
    assert all(link.startswith("https://") for link in requested)


def test_without_hydrolakes_the_lakes_are_natural_earths(tmp_path, offline):
    requested, opener = offline
    layers = water.build_layers(tmp_path / "cache", with_hydrolakes=False, opener=opener)
    lakes = layers[1]
    assert lakes.columns["name"] == ["Lake Small", "Lake Ontario"]
    assert not any("wikidata" in link for link in requested)
