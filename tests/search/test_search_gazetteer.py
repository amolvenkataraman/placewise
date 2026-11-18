"""Location search with packs: the Gazetteer over forward search, and the top-level names."""

import pytest
from search_kit import geocoder

import placewise
from placewise import engine
from placewise.search import SearchGazetteer
from placewise.text import Gazetteer


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    return geocoder(tmp_path_factory.mktemp("gazetteer"))


def test_gazetteer_confirms_settlements_by_exact_name(geo):
    gaz = SearchGazetteer(geo)
    assert isinstance(gaz, Gazetteer)
    place = gaz.match("Alpha City", None, None)
    assert place.id == "town:alpha-city" and place.point is not None and place.bbox is not None
    assert place.codes["iso2"] == "XA" and place.codes["admin1"] == "N"
    assert gaz.match("Alpha Citty", None, None) is None  # a typo is not a confirmation
    assert gaz.match("Alpha Falls", None, None) is None  # a park is not a city
    assert gaz.match("Nowhere", None, None) is None


def test_top_level_find_get_suggest_use_the_default_geocoder(geo, monkeypatch):
    monkeypatch.setattr(engine, "_default", geo)
    assert placewise.find("Alpha City")[0].place.id == "town:alpha-city"
    assert placewise.get("parks:ALFA").place.name == "Alpha Falls National Park"
    assert placewise.suggest("Rivert", limit=1)[0].place.id == "town:riverton"
    assert placewise.suggest("Rivert", admin1="XB-W")[0].place.id == "geonames:5"
    assert {"find", "get", "suggest"} <= set(placewise.__all__)
