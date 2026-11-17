from pathlib import Path

import pytest
from india_fixtures import (
    CHARMINAR,
    GATEWAY_OF_INDIA,
    INDIA_GATE,
    MG_ROAD,
    NWDP_STATES,
    write_boundaries,
    write_directory,
    write_nwdp_geojson,
)
from regions_kit import IN_REGIONS, use_regions

from packbuild import india
from packbuild.sources import SOURCES

LAYERS = ["pincodes", "post_offices", "regions"]


@pytest.fixture
def downloads(tmp_path):
    store = tmp_path / "downloads"
    store.mkdir()
    return {
        "All_India_pincode_Boundary-19312.geojson": write_boundaries(
            store / "All_India_pincode_Boundary-19312.geojson"
        ),
        "pincode.csv": write_directory(store / "pincode.csv"),
    }


@pytest.fixture
def offline(downloads, monkeypatch):
    """fetch() replaced by fixture files named like the real downloads; no network."""
    requested = []

    def fake_fetch(url, cache_dir, refresh=False):
        requested.append(url)
        return downloads[url.rsplit("/", 1)[1]]

    monkeypatch.setattr(india, "fetch", fake_fetch)
    use_regions(monkeypatch, IN_REGIONS)
    return requested


def test_build_india_fetches_both_sources_from_the_registry(tmp_path, offline, monkeypatch):
    calls = []

    def fake_write_pack(out_dir, name, version, layers, created=None):
        calls.append((name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(india, "write_pack", fake_write_pack)
    out = india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "in-2026.11"
    assert offline == [
        SOURCES["indiapost-pincode-boundary"].downloads["boundary_mirror"],
        SOURCES["indiapost-pincode-directory"].downloads["directory_mirror"],
    ]
    [(name, version, layers)] = calls
    assert (name, version) == ("in", "2026.11")
    assert [layer.name for layer in layers] == LAYERS
    for layer in layers:
        assert set(layer.sources) <= set(SOURCES)
        assert {"id", "name"} <= set(layer.columns) and set(layer.columns) == set(layer.types)


def test_build_india_writes_a_pack_that_answers_the_spot_checks(tmp_path, offline):
    from placewise.packs import open_pack

    path = india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")
    pack = open_pack(path, verify=True)
    assert [layer.name for layer in pack] == LAYERS
    assert set(pack.sources) == {
        "indiapost-pincode-boundary",
        "indiapost-pincode-directory",
        "placewise-regions",
    }
    pincodes = pack["pincodes"]

    def at(point):
        i = pincodes.query(*point)
        return pincodes.row(int(i)) if i >= 0 else None

    assert at(MG_ROAD)["id"] == "pin:560001"
    assert (at(MG_ROAD)["district"], at(MG_ROAD)["state_code"]) == ("BENGALURU URBAN", "IN-KA")
    assert (at(GATEWAY_OF_INDIA)["pincode"], at(GATEWAY_OF_INDIA)["district"]) == ("400001", "MUMBAI")
    assert at(CHARMINAR)["state"] == "TELANGANA"
    assert at(INDIA_GATE)["state_code"] == "IN-DL"
    assert at((20.0, 75.0)) is None
    offices = pack["post_offices"]
    i, km = offices.nearest(*CHARMINAR)
    assert offices.value("name", i) == "Charminar S.O" and km < 0.01
    assert offices.value("delivery", i) is True
    regions = pack["regions"]
    assert [regions.value("id", i) for i in regions.query_all(*INDIA_GATE)] == ["region:test-delhi"]
    assert regions.query_all(*MG_ROAD) == []
    assert regions.value("members", 0) == "pin:110001"


def test_region_districts_must_match_their_pin_areas(tmp_path, offline, monkeypatch):
    use_regions(monkeypatch, [{**IN_REGIONS[0], "districts": {"DL": ["NEW DELHI", "SHAHDARA"]}}])
    with pytest.raises(ValueError, match="no PIN area in DL SHAHDARA"):
        india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")
    use_regions(monkeypatch, [{**IN_REGIONS[0], "members": ["pin:110001", "pin:560001"]}])
    with pytest.raises(ValueError, match="not in its districts: pin:560001"):
        india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")


def test_manually_downloaded_files_skip_the_download(tmp_path, downloads, offline):
    path = india.build_india(
        tmp_path / "cache",
        tmp_path / "out",
        "2026.11",
        pincode_boundaries=downloads["All_India_pincode_Boundary-19312.geojson"],
        pincode_directory=downloads["pincode.csv"],
    )
    assert offline == []
    assert (path / "pincodes" / "layer.json").is_file()


def test_one_manual_file_still_fetches_the_other(tmp_path, downloads, offline, monkeypatch):
    monkeypatch.setattr(india, "write_pack", lambda out_dir, name, version, layers: layers)
    layers = india.build_india(
        tmp_path / "c", tmp_path / "o", "2026.11", pincode_directory=downloads["pincode.csv"]
    )
    assert offline == [SOURCES["indiapost-pincode-boundary"].downloads["boundary_mirror"]]
    assert len(layers[0].columns["id"]) == 5


def test_state_boundaries_need_a_cleared_registry_entry(tmp_path, offline):
    states = write_nwdp_geojson(tmp_path / "state.geojson", NWDP_STATES)
    with pytest.raises(ValueError, match=r"nwdp-soi-boundaries.*registry"):
        india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11", states=states)
    assert not (tmp_path / "out").exists()


def test_cli_passes_manual_paths(tmp_path, monkeypatch):
    seen = {}

    def fake_build(cache_dir, out_dir, version, refresh=False, **paths):
        seen.update(paths, version=version, refresh=refresh)
        return Path(out_dir) / f"in-{version}"

    monkeypatch.setattr(india, "build_india", fake_build)
    india.main(["--version", "2026.11", "--pincode-boundaries", "b.geojson", "--pincode-directory", "d.csv"])
    assert seen["pincode_boundaries"] == Path("b.geojson") and seen["pincode_directory"] == Path("d.csv")
    assert seen["states"] is None and seen["version"] == "2026.11" and seen["refresh"] is False
