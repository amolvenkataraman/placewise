"""The park pack builders (packbuild.parks) on the synthetic inputs of parks_fixtures."""

import parks_fixtures as fx
import pytest

from packbuild import parks
from packbuild.sources.parks import cpcad, nps, padus, usfs, wikidata
from placewise.engine._within import Parks
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
    result = fx.wikidata_result(
        tmp_path / "np.json", [("Q10", "Gamma National Park", -139.6, 2.25, 78.54e6, "XC", 40)]
    )
    monkeypatch.setattr(wikidata, "fetch", lambda cache, refresh=False: {"parks_national": result})
    return tmp_path


def test_usa_parks_pack(inputs):
    path = parks.build("usa", inputs / "cache", inputs / "out", "2026.11")
    assert path.name == "usa-parks-2026.11"
    pack = open_pack(path, verify=True)
    assert list(pack.layers) == ["parks_national", "parks_state", "parks_regional", "parks_local"]
    assert set(pack.sources) == {"nps-boundaries", "usfs-forests", "padus"}
    national = pack["parks_national"]
    hits = national.query_all(0.75, -139.75)
    assert [national.value("id", i) for i in hits] == ["nps:ALPH"]
    assert national.value("aliases", hits[0]) == "Alpha" and national.value("code", hits[0]) == "ALPH"
    state = pack["parks_state"]
    assert {state.value("park", i) for i in state.query_all(0.75, -139.75)} == {"usfs:0101"}
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


def test_the_engine_reads_the_built_packs(inputs):
    packs = [open_pack(parks.build(r, inputs / "cache", inputs / "out", "2026.11")) for r in ("usa", "world")]

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
    assert "usa-parks/parks_local" in layers.keys


def test_main_builds_the_named_packs(inputs, capsys):
    parks.main(
        ["world", "--cache-dir", str(inputs / "cache"), "--out", str(inputs / "out"), "--version", "2026.11"]
    )
    assert capsys.readouterr().out.strip().endswith("world-parks-2026.11")
