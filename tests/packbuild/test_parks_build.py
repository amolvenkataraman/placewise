"""The park pack builders (packbuild.parks) on the synthetic inputs of parks_fixtures."""

import json

import parks_fixtures as fx
import pytest
from natda_kit import write_natda

from packbuild import parks
from packbuild.sources.parks import cpcad, eea, wikidata
from packbuild.sources.parks.usa import nps, padus, usfs
from placewise.engine._nearby.parks import Parks
from placewise.packs import open_pack


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(nps, "fetch", lambda cache, refresh=False: fx.nps_pages(tmp_path / "nps"))
    monkeypatch.setattr(usfs, "fetch", lambda cache, refresh=False: fx.usfs_shapefile(tmp_path / "usfs"))
    monkeypatch.setattr(
        padus, "fetch",
        lambda cache, refresh=False: (fx.padus_fee_pages(tmp_path / "fee"), fx.padus_refuge_pages(tmp_path / "nwr")),  # noqa: E501
    )  # fmt: skip
    monkeypatch.setattr(cpcad, "fetch", lambda cache, refresh=False: fx.cpcad_pages(tmp_path / "cpcad"))
    monkeypatch.setattr(eea, "fetch", lambda cache, refresh=False: write_natda(tmp_path / "natda"))
    result = fx.wikidata_result(
        tmp_path / "np.json", [("Q10", "Gamma National Park", -139.6, 2.25, 78.54e6, "XC", 40)]
    )
    monkeypatch.setattr(wikidata, "fetch", lambda cache, refresh=False: {"parks_national": result})
    return tmp_path


def test_usa_parks_pack(inputs):
    path = parks.build("usa", inputs / "cache", inputs / "out", "2026.11")
    assert path.name == "usa-parks-2026.11"
    pack = open_pack(path, verify=True)
    assert list(pack.layers) == ["parks_national", "parks_state", "parks_regional"]  # local: usa-parks-local
    assert set(pack.sources) == {"nps-boundaries", "usfs-forests", "padus"}
    national = pack["parks_national"]
    hits = national.query_all(0.75, -139.75)
    assert [national.value("id", i) for i in hits] == ["nps:ALPH"]
    assert national.value("aliases", hits[0]) == "Alpha" and national.value("code", hits[0]) == "ALPH"
    assert pack.names.exact("Alpha").row.tolist()[:1] == [hits[0]]
    assert {pack.names.layers[x] for x in pack.names.codes("ALPH").layer} == {"parks_national"}
    state = pack["parks_state"]
    assert {state.value("park", i) for i in state.query_all(0.75, -139.75)} == {"usfs:0101"}
    assert "kind" not in json.loads((path / "pack.json").read_text())  # its name says it all


def test_usa_parks_local_pack(inputs):
    path = parks.build("usa-local", inputs / "cache", inputs / "out", "2026.11")
    assert path.name == "usa-parks-local-2026.11"
    pack = open_pack(path, verify=True)
    assert list(pack.layers) == ["parks_local"]
    manifest = json.loads((path / "pack.json").read_text())
    assert (manifest["kind"], manifest["covers"], manifest["requires"]) == ("parks", ["US"], ["usa-parks"])
    local = pack["parks_local"]
    rows = [local.row(i) for i in range(len(local))]
    green = [r for r in rows if r["name"] == "Central Green"]
    assert len(green) == 3 and len({r["park"] for r in green}) == 2
    assert len({r["id"] for r in green}) == 3  # row ids are unique: the park id, then #2


def test_can_and_world_packs(inputs):
    can = open_pack(parks.build("can", inputs / "cache", inputs / "out", "2026.11"))
    assert can.name == "can-parks" and can.sources == ("cpcad",)
    world = open_pack(parks.build("world", inputs / "cache", inputs / "out", "2026.11"))
    assert list(world.layers) == ["park_points"] and world.sources == ("wikidata",)
    assert world["park_points"].value("radius_km", 0) == pytest.approx(5.0, rel=1e-3)


def test_eur_parks_pack(inputs):
    path = parks.build("eur", inputs / "cache", inputs / "out", "2026.11")
    assert path.name == "eur-parks-2026.11"
    pack = open_pack(path, verify=True)
    assert list(pack.layers) == ["parks_national", "parks_state", "parks_regional"]
    assert set(pack.sources) == {"eea-natda", "wikidata"}  # Wikidata: the English names
    assert pack["parks_state"].sources == ("eea-natda",)  # no English name there
    manifest = json.loads((path / "pack.json").read_text())
    assert (manifest["kind"], manifest["covers"]) == ("parks", ["GR", "XX"])
    assert "requires" not in manifest
    national = pack["parks_national"]
    hits = national.query_all(45.25, -9.9)  # in Alpha's core zone, a row of the Alpha park
    assert [national.value("park", i) for i in hits] == ["eea:101"]
    assert national.value("name", hits[0]) == "Alpha National Park"
    assert pack.names.exact("Alpha").row.tolist()  # the short name, and the national ones, are aliases
    assert pack.names.exact("Nationalpark Alpha Kernzone").row.tolist()


def test_the_engine_reads_the_built_packs(inputs):
    regions = ("usa", "usa-local", "world")
    packs = [open_pack(parks.build(r, inputs / "cache", inputs / "out", "2026.11")) for r in regions]

    class Layers:  # the part of engine._layers.Layers that Parks uses
        def __init__(self):
            self.keys = []

        def add(self, pack, name, maker=None):
            self.keys.append(f"{pack.name}/{name}")
            return self.keys[-1]

    layers = Layers()
    found = Parks(
        packs, layers, type("Near", (), {"park_tier1": 25.0, "park_tier2": 10.0, "park_tier3": 1.0})
    )
    assert found and layers.keys[-1] == "world-parks/park_points"
    assert "usa-parks-local/parks_local" in layers.keys


def test_main_builds_the_named_packs(inputs, capsys):
    parks.main(
        ["world", "--cache-dir", str(inputs / "cache"), "--out", str(inputs / "out"), "--version", "2026.11"]
    )
    assert capsys.readouterr().out.strip().endswith("world-parks-2026.11")
