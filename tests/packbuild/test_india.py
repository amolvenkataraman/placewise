"""The India pack build over tiny fixtures: PIN areas round public landmarks (india_fixtures), LGD
reports for them (ind_kit), a curated names file, and Natural Earth countries as two boxes (India,
and a neighbour holding the eastern part of Leh's PIN box). No network."""

import json
from pathlib import Path

import pytest
from ind_kit import write_lgd
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
from packbuild.ind import names as ind_names
from packbuild.layer import LayerData
from packbuild.sources import SOURCES
from placewise.model import Feature, Outline

LAYERS = ["states", "districts", "cities", "pincodes", "post_offices", "neighbourhoods", "regions"]
LEH_CLAIMED = (34.15, 77.63)  # in Leh's PIN box, on the neighbour's ground
LEH = (34.15, 77.55)
SOURCE = {"title": "test", "url": "https://example.org"}


def _box(south, west, north, east):
    return Feature(
        (
            Outline(
                (((south, west), (north, west), (north, east), (south, east)),),
            ),
        ),
        {},
        "",
    )


def countries():
    return LayerData(
        "countries",
        "polygon",
        {"id": ["iso:IN", "iso:XO"], "name": ["India", "Otherland"], "adm0_a3": ["IND", "XOO"]},
        ("naturalearth",),
        features=[_box(6, 68, 34.12, 98), _box(34.12, 77.6, 36, 80)],
    )


def write_names(path):
    doc = {
        "_comment": "test",
        "units": [
            {
                "lgd": "district:572",
                "name": "Bengaluru Urban",
                "former": [{"name": "Bangalore Urban", "until": "2014"}],
                "source": SOURCE,
            }
        ],
        "cities": [
            {
                "id": "lgd:ulb:276600",
                "name": "Bengaluru",
                "official_name": "Bruhat Bengaluru Mahanagara Palike",
                "state": "KA",
                "lgd": ["276600"],
                "pincodes": ["560001"],
                "aliases": ["Bangalore"],
                "source": SOURCE,
            }
        ],
        "not_neighbourhoods": ["Rajbhavan"],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.fixture
def downloads(tmp_path):
    store = tmp_path / "downloads"
    store.mkdir()
    return {
        "All_India_pincode_Boundary-19312.geojson": write_boundaries(
            store / "All_India_pincode_Boundary-19312.geojson"
        ),
        "pincode.csv": write_directory(store / "pincode.csv"),
        "lgd": store / "lgd",
    }


@pytest.fixture
def offline(downloads, monkeypatch):
    """fetch() replaced by fixture files named like the real downloads; no network."""
    requested = []

    def fake_fetch(url, cache_dir, refresh=False):
        requested.append(url)
        return downloads[url.rsplit("/", 1)[1]]

    monkeypatch.setattr(india, "fetch", fake_fetch)
    monkeypatch.setattr(india.lgd, "download", lambda cache_dir, refresh=False: write_lgd(downloads["lgd"]))
    monkeypatch.setattr(india, "_countries", lambda cache_dir, refresh: countries())
    monkeypatch.setattr(ind_names, "DATASET", write_names(downloads["lgd"].parent / "ind.json"))
    use_regions(monkeypatch, IN_REGIONS)
    return requested


def test_build_india_fetches_both_sources_from_the_registry(tmp_path, offline, monkeypatch):
    calls = []

    def fake_write_pack(out_dir, name, version, layers, created=None, names=None):
        assert names is not None and len(names) > 0  # every pack carries a name index
        calls.append((name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(india, "write_pack", fake_write_pack)
    out = india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "ind-2026.11"
    assert offline == [
        SOURCES["indiapost-pincode-boundary"].downloads["boundary_mirror"],
        SOURCES["indiapost-pincode-directory"].downloads["directory_mirror"],
    ]
    [(name, version, layers)] = calls
    assert (name, version) == ("ind", "2026.11")
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
        "lgd-directory",
        "placewise-names",
        "naturalearth",
        "placewise-regions",
    }
    pincodes = pack["pincodes"]

    def at(point):
        i = pincodes.query(*point)
        return pincodes.row(int(i)) if i >= 0 else None

    assert at(MG_ROAD)["id"] == "pin:560001"
    pin = pack.names.codes("560001")
    assert [pack.names.layers[x] for x in pin.layer] == ["pincodes"]
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


def test_build_keeps_only_offices_in_or_near_their_own_pin_area(tmp_path, offline, caplog):
    import logging

    from placewise.packs import open_pack

    with caplog.at_level(logging.INFO):
        path = india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")
    offices = open_pack(path)["post_offices"]
    names = [offices.value("name", i) for i in range(len(offices))]
    # every fixture office with usable coordinates is in its PIN box, except Silvassa, whose PIN
    # code 396230 has no polygon
    assert len(names) == 8 and "Silvassa S.O" not in names
    assert "kept 8 of 9 offices" in caplog.text


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
    monkeypatch.setattr(india, "write_pack", lambda out_dir, name, version, layers, names=None: layers)
    layers = india.build_india(
        tmp_path / "c", tmp_path / "o", "2026.11", pincode_directory=downloads["pincode.csv"]
    )
    assert offline == [SOURCES["indiapost-pincode-boundary"].downloads["boundary_mirror"]]
    pincodes = next(layer for layer in layers if layer.name == "pincodes")
    assert len(pincodes.columns["id"]) == 6  # five PIN areas, Leh's in two pieces


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


def test_lgd_keyed_layers_from_pin_areas(tmp_path, offline):
    from placewise.packs import open_pack

    pack = open_pack(india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11"), verify=True)

    def at(layer, point):
        i = int(pack[layer].query(*point))
        return pack[layer].row(i) if i >= 0 else None

    assert (at("states", MG_ROAD)["id"], at("states", MG_ROAD)["iso"]) == ("lgd:state:29", "IN-KA")
    assert at("districts", MG_ROAD)["name"] == "Bengaluru Urban"
    assert at("districts", MG_ROAD)["aliases"] == "Bangalore Urban"
    bengaluru = at("cities", MG_ROAD)  # seeded by the curated dataset: LGD lists no PIN code for it
    assert (bengaluru["id"], bengaluru["name"], bengaluru["aliases"]) == (
        "lgd:ulb:276600",
        "Bengaluru",
        "Bangalore",
    )
    assert at("cities", GATEWAY_OF_INDIA)["name"] == "Greater Mumbai"
    assert at("cities", INDIA_GATE)["name"] == "New Delhi"  # LGD's NDMC, its type words dropped
    assert at("cities", LEH) is None  # Leh's PIN area is too big to be part of a town
    pin = at("pincodes", MG_ROAD)
    assert (pin["lgd_district"], pin["city"], pin["india_view_only"]) == ("572", "lgd:ulb:276600", False)
    hoods = pack["neighbourhoods"]
    # offices named like their city (Bengaluru G.P.O.) or an institution (Rajbhavan) are left out;
    # "Mumbai" stays because the fixture's city is LGD's "Greater Mumbai" (the dataset renames it)
    got = [(hoods.value("name", i), hoods.value("city", i)) for i in range(len(hoods))]
    assert got == [
        ("Vidhana Soudha", "lgd:ulb:276600"),
        ("Mumbai", "lgd:ulb:251488"),
        ("Charminar", "lgd:ulb:251664"),
        ("Parliament House", "lgd:ulb:276447"),
    ]


def test_pin_areas_on_a_neighbours_ground_are_for_indias_view_only(tmp_path, offline):
    from placewise.packs import open_pack

    pack = open_pack(india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11"))
    for layer, ident in (
        ("pincodes", "pin:194101"),
        ("states", "lgd:state:37"),
        ("districts", "lgd:district:39"),
    ):
        claimed, own = (
            pack[layer].row(int(pack[layer].query(*LEH_CLAIMED))),
            pack[layer].row(int(pack[layer].query(*LEH))),
        )
        assert (own["id"], own["india_view_only"]) == (ident, False)
        assert (claimed["id"], claimed["india_view_only"]) == (f"{ident}#india-view", True)


def test_regions_by_lgd_units_must_match_the_crosswalk(tmp_path, offline, monkeypatch):
    leh = {**IN_REGIONS[0], "id": "region:test-leh", "admin1": ["LA"], "lgd_units": ["subdistrict:6201"]}
    del leh["districts"]
    use_regions(monkeypatch, [{**leh, "members": ["pin:194101"]}])
    india.build_india(tmp_path / "cache", tmp_path / "out", "2026.11")
    use_regions(monkeypatch, [{**leh, "members": ["pin:194101", "pin:110001"]}])
    with pytest.raises(ValueError, match="not in its LGD units: pin:110001"):
        india.build_india(tmp_path / "cache", tmp_path / "out2", "2026.11")
    use_regions(
        monkeypatch, [{**leh, "members": ["pin:110001"], "lgd_units": ["subdistrict:6201", "district:1"]}]
    )
    with pytest.raises(ValueError, match=r"(?s)no PIN area in LGD district:1.*missing pin:194101"):
        india.build_india(tmp_path / "cache", tmp_path / "out3", "2026.11")
