"""`placewise find` through main(argv): options handed to search, cards and JSON."""

import json

import pytest

from placewise.cli import _common, main
from tests.search.search_kit import geocoder


@pytest.fixture
def geo(tmp_path, monkeypatch):
    built = geocoder(tmp_path / "packs")
    monkeypatch.setattr(_common, "open_geocoder", lambda args: built)
    return built


def test_find_prints_entity_cards(geo, capsys):
    assert main(["find", "Alpha City"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("1. Alpha City  (North Province, XA)")
    cards = out.split("\n\n")
    first = {line.split()[0]: line for line in cards[0].splitlines()[1:]}
    assert first["kind"].split() == ["kind", "locality"]
    assert first["id"].split()[:2] == ["id", "town:alpha-city"] and first["alternates"].split()[1] == "2:"
    assert "radius" in first["extent"] and "score" in first and "point" in first
    assert "\x1b[" not in out and max(len(line) for line in out.splitlines()) <= 100
    assert main(["find", "Riverton"]) == 0
    cards = capsys.readouterr().out.split("\n\n")
    assert len(cards) == 2 and cards[0].startswith("1. Riverton") and cards[1].startswith("2. Riverton")


def test_find_json_and_context_options(geo, capsys):
    assert main(["find", "Riverton", "--state", "XB-W", "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert [e["place"]["id"] for e in found] == ["geonames:5"]
    assert main(["find", "Riverton", "--near", "0.5,-138.7", "--limit", "1", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["place"]["id"] == "geonames:5"
    assert main(["find", "XAI", "--kind", "airport", "--json", "--geometry"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["place"]["kind"] == "airport"


def test_find_nothing_and_bad_options(geo, capsys):
    assert main(["find", "Nowhere At All Whatsoever"]) == 1
    assert "nothing found" in capsys.readouterr().err
    assert main(["find", "Riverton", "--near", "nope"]) == 2
    assert main(["find", "Riverton", "--kind", "volcano-ish"]) == 1
    assert "unknown kind" in capsys.readouterr().err
