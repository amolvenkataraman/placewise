"""packbuild.sources.water.hydrolakes: the largest HydroLAKES polygons, fetched as a prefix of the
archive's .shp, with names given the generic they lack."""

import json

import pytest
from hydrolakes_kit import URL, opener_for, write_archive

from packbuild.sources.water import hydrolakes
from packbuild.sources.water.ranged_zip import RangeIgnoredError


@pytest.fixture
def fetched(tmp_path):
    (tmp_path / "remote").mkdir()
    archive = write_archive(tmp_path / "remote")
    served = []
    cache = tmp_path / "cache"
    found = hydrolakes.fetch_largest(URL, cache, min_area_km2=10, opener=opener_for(archive, served))
    return found, served, archive, cache


def test_only_the_records_kept_are_downloaded(fetched):
    (shp, dbf, count), _served, _archive, cache = fetched
    assert count == 5  # lakes of 10 km² or more are the first five records
    assert shp.parent == cache / "HydroLAKES_polys_v10_shp" and dbf.suffix == ".dbf"
    sidecar = json.loads(shp.with_name(shp.name + ".json").read_text())
    assert sidecar["url"] == URL and sidecar["records"] == 5 and sidecar["min_area_km2"] == 10
    assert len(sidecar["sha256"]) == 64 and sidecar["retrieved"]


def test_a_second_fetch_uses_the_cache(fetched):
    (shp, dbf, count), served, archive, cache = fetched
    served.clear()
    again = hydrolakes.fetch_largest(URL, cache, min_area_km2=10, opener=opener_for(archive, served))
    assert again == (shp, dbf, count) and served == []


def _ignoring_ranges(asked, first, last):
    raise RangeIgnoredError(f"{asked}: the server ignored the range request (HTTP 200)")


def _whole_from(archive, calls):
    def whole(asked):
        calls.append(asked)
        data = archive.read_bytes()
        return iter([data[: len(data) // 2], data[len(data) // 2 :]])

    return whole


def test_a_server_ignoring_ranges_gets_the_whole_zip_once_then_deleted(tmp_path, fetched):
    (shp, _dbf, count), _, archive, _ = fetched
    calls, cache = [], tmp_path / "cache2"
    found = hydrolakes.fetch_largest(
        URL, cache, min_area_km2=10, opener=_ignoring_ranges, whole=_whole_from(archive, calls)
    )
    assert calls == [URL] and found[2] == count
    assert found[0].read_bytes() == shp.read_bytes()  # the same prefix as the ranged path
    folder = cache / "HydroLAKES_polys_v10_shp"
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        [
            found[0].name,
            found[0].name + ".json",
            *(f"HydroLAKES_polys_v10{e}" for e in (".dbf", ".shx", ".prj")),
        ]
    )  # the 820 MB zip is not kept
    layer = hydrolakes.lakes(found[0], found[1], found[2], tolerance_m=0)
    assert len(layer.columns["id"]) == count


def test_the_ranged_path_never_downloads_the_whole_zip(tmp_path, fetched):
    _, _, archive, _ = fetched
    calls = []
    hydrolakes.fetch_largest(
        URL, tmp_path / "c3", min_area_km2=10, opener=opener_for(archive), whole=_whole_from(archive, calls)
    )
    assert calls == []


def test_lakes_read_the_kept_records_with_ids_types_and_names(fetched):
    (shp, dbf, count), _, _, _ = fetched
    layer = hydrolakes.lakes(shp, dbf, count, tolerance_m=0)
    assert layer.columns["id"] == [f"hydrolakes:{i}" for i in (1, 2, 3, 4, 5)]
    assert layer.columns["name"] == ["Lake Ontario", "", "Lake Tahoe", "", ""]
    assert layer.columns["type"] == ["lake", "reservoir", "lake", "lake", "lake"]
    assert layer.columns["area_km2"][0] == pytest.approx(19347.36)
    assert layer.columns["elevation_m"] == [75.0, 187.0, 1898.0, 1583.0, 0.0]  # the lake's surface
    assert layer.types["elevation_m"] == "f8"
    assert set(layer.columns["source"]) == {"hydrolakes"}
    assert layer.features[2].contains(39.0, -120.0)
    assert "country" not in layer.columns  # HydroLAKES' country is the outflow's: never used


@pytest.mark.parametrize(
    ("name", "kind", "english"),
    [
        ("Ontario", "lake", "Lake Ontario"),
        ("Dall Lake", "lake", "Dall Lake"),
        ("Lac a L'Eau Claire", "lake", "Lac a L'Eau Claire"),
        ("Hirakud Reservoir", "reservoir", "Hirakud Reservoir"),
        ("Pangong", "lake", "Lake Pangong"),
        ("Sardar Sarovar", "reservoir", "Sardar Sarovar"),
        ("Kariba", "reservoir", "Kariba Reservoir"),
        ("", "lake", ""),
    ],
)
def test_names_gain_their_generic(name, kind, english):
    assert hydrolakes.english_name(name, kind) == english
