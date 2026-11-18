"""The world-notable pack builder (packbuild.notable) on the synthetic inputs of notable_fixtures."""

import notable_fixtures as fx
import pytest

from packbuild import notable
from packbuild.sources.notable import rank
from placewise.packs import open_pack


@pytest.fixture
def pack(tmp_path, monkeypatch):
    monkeypatch.setattr(rank, "MIN_VIEWS", 1000)
    cache = fx.write_cache(tmp_path / "cache")
    return open_pack(notable.build(cache, tmp_path / "out", "2026.11"), verify=True)


def rows(pack):
    layer = pack["notable"]
    return {layer.value("id", i): layer.row(i) for i in range(len(layer))}


def test_pack_layout(pack):
    assert pack.name == "world-notable" and list(pack.layers) == ["notable"]
    assert set(pack.sources) == {"wikidata", "qrank"}
    layer = pack["notable"]
    assert layer.kind == "point"
    columns = (
        "id",
        "name",
        "aliases",
        "kind",
        "fame",
        "country",
        "sitelinks",
        "iata",
        "icao",
        "ipeds",
        "aishe",
    )
    assert set(layer.fields) >= {*columns, "station_code"}


def test_rows(pack):
    found = rows(pack)
    # Q2 is the same station 15 m away and less known: dropped, its codes and names joining Q1;
    # Q7 is a defence aerodrome; Q6 sits in two countries, so it has none
    assert sorted(found, key=lambda i: int(i.split("Q")[1])) == [
        "wikidata:Q1", "wikidata:Q3", "wikidata:Q4", "wikidata:Q5", "wikidata:Q6"
    ]  # fmt: skip
    station = found["wikidata:Q1"]
    assert station["kind"] == "station" and station["station_code"] == "ACL" and station["country"] == "XA"
    assert station["aliases"].split("|") == ["Alpha Central station", "Alpha Central", "Old Central Building"]
    airport = found["wikidata:Q5"]
    assert (airport["iata"], airport["icao"], airport["aliases"]) == ("AAA", "XAAA", "Alpha Airport")
    museum = found["wikidata:Q3"]
    assert museum["kind"] == "museum" and museum["aliases"] == "AM"
    assert found["wikidata:Q6"]["country"] is None  # row() reads "" as None
    assert found["wikidata:Q4"]["sitelinks"] == 90


def test_fame_is_within_the_kind_among_kept_places(pack):
    found = rows(pack)
    # one place of each of station, museum, airport; two landmarks
    assert found["wikidata:Q1"]["fame"] == found["wikidata:Q3"]["fame"] == found["wikidata:Q5"]["fame"] == 1.0
    assert found["wikidata:Q4"]["fame"] == 1.0 and found["wikidata:Q6"]["fame"] == 0.5


def test_page_view_floor(tmp_path, monkeypatch):
    monkeypatch.setattr(rank, "MIN_VIEWS", 10_000)  # Q6 (5,000 views) goes
    cache = fx.write_cache(tmp_path / "cache")
    pack = open_pack(notable.build(cache, tmp_path / "out", "2026.11"))
    assert "wikidata:Q6" not in rows(pack)


def test_name_index(pack):
    from placewise.constants.names import PLACE_KINDS

    idx = pack.names
    station = idx.exact("Alpha Central station")  # a short name the build adds
    assert len(station) == 1 and PLACE_KINDS[int(station.kind[0])] == "station"
    assert pack["notable"].value("id", int(station.row[0])) == "wikidata:Q1"
    tower = idx.exact("Alpha Tower")
    assert PLACE_KINDS[int(tower.kind[0])] == "landmark" and tower.rank[0] == pytest.approx(0.85)
    assert len(idx.codes("AAA")) == 1 and len(idx.codes("Q4")) == 1  # IATA code; Wikidata id
