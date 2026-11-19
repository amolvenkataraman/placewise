"""packbuild.sources.water.gdw: Global Dam Watch reservoirs as the world-water pack's
`reservoirs` layer, offline."""

import pytest
from gdw_kit import write_archive

from packbuild.sources.water import gdw
from placewise.constants import water as const


@pytest.fixture
def shp(tmp_path):
    (tmp_path / "remote").mkdir()
    return gdw.extract(write_archive(tmp_path / "remote"), tmp_path / "cache")


def test_extract_takes_the_reservoir_files_once(tmp_path, shp):
    assert shp == tmp_path / "cache" / "GDW_reservoirs_v1_0.shp"
    assert sorted(p.name for p in shp.parent.iterdir()) == [
        "GDW_reservoirs_v1_0.dbf",
        "GDW_reservoirs_v1_0.shp",
    ]
    before = shp.stat().st_mtime_ns
    assert gdw.extract(tmp_path / "remote" / "47913754", tmp_path / "cache") == shp
    assert shp.stat().st_mtime_ns == before


def test_reservoirs_keep_named_big_dam_made_ones(shp):
    layer = gdw.reservoirs(shp, min_area_km2=10.0, tolerance_m=30.0)
    assert layer.name == const.RESERVOIRS and layer.kind == "polygon" and layer.sources == ("gdw",)
    c = layer.columns
    # smallest first; the lake behind a control dam (Tahoe), the unnamed and the small are left out
    assert c["name"] == ["Big Meadows Reservoir", "Tehri Reservoir", "Nagarjuna Sagar", "Hirakud Reservoir"]
    assert c["id"] == ["gdw:11543", "gdw:1687", "gdw:351", "gdw:336"]
    assert set(c["type"]) == {const.RESERVOIR} and set(c["source"]) == {"gdw"}
    assert c["area_km2"] == [12.0, 18.9, 195.2, 499.5]
    assert len(layer.features) == 4 and layer.features[1].id == "gdw:1687"


@pytest.mark.parametrize(
    ("res", "dam", "name"),
    [
        ("Lake Mead", "Hoover", "Lake Mead"),
        ("Hirakud", "Hirakud", "Hirakud Reservoir"),
        ("Nagarjuna", "Nagarjuna Sagar", "Nagarjuna Sagar"),  # the dam's name says the water
        ("", "Tehri", "Tehri Reservoir"),
        ("", "El Vado Reservoir Dam", "El Vado Reservoir"),
        ("", "LAKE MEADE DAM", "Lake Meade"),
        ("", "BIG MEADOWS - MAIN DAM", "Big Meadows Reservoir"),
        ("", "Eugene J. Burrell Lock and Dam", "Eugene J. Burrell Reservoir"),
        ("", "Hinakud Dam", "Hirakud Reservoir"),  # constants.water.NAME_FIXES
        ("", "Dam", ""),
        ("", "West Forebay Dike GJ-18", ""),  # a structure, not a body of water
        ("", "Structure 59", ""),
        ("", "Waboose Lake Main Sluice", ""),
        ("", "", ""),
    ],
)
def test_english_name(res, dam, name):
    assert gdw.english_name(res, dam) == name
