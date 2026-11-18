"""`placewise find` through main(argv): options handed to search, cards and JSON."""

import json

import pytest

from placewise.cli import find as find_cli
from placewise.cli import main
from tests.search.search_kit import geocoder


@pytest.fixture
def geo(tmp_path, monkeypatch):
    built = geocoder(tmp_path / "packs")
    monkeypatch.setattr(find_cli, "_geocoder", lambda args: built)
    return built


def test_find_prints_result_cards(geo, capsys):
    assert main(["find", "Alpha City"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("1. Alpha City  (North Province, XA)")
    assert "locality · town:alpha-city" in out and "same place in" in out and "radius" in out


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
