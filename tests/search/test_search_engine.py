"""Forward search on the synthetic world (search_kit): ranking, merging, context, codes, ids."""

import pytest
from search_kit import ALPHA_CITY_BOX, PARK_BOX, geocoder

from placewise.model import Layer, PlaceKind
from placewise.overrides import OverrideEngine


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    return geocoder(tmp_path_factory.mktemp("search"))


def ids(entities):
    return [e.place.id for e in entities]


def test_city_found_in_three_packs_is_one_answer_under_its_outline(geo):
    found = geo.find("Alpha City")
    top = found[0]
    assert top.place.id == "town:alpha-city" and top.place.kind is PlaceKind.LOCALITY
    assert {p.id for p in top.alternates} == {"geonames:1", "metro:alpha-city"}
    assert len(found) == 1
    s, w, n, e = ALPHA_CITY_BOX
    assert s <= top.point.lat <= n and w <= top.point.lon <= e
    assert top.bbox.as_tuple() == pytest.approx(ALPHA_CITY_BOX)
    assert top.region == "North Province" and top.country == "XA" and top.city is None
    assert top.place.codes["iso2"] == "XA" and top.place.codes["admin1"] == "N"
    assert 0 < top.score


def test_same_name_in_two_countries_bigger_first(geo):
    found = geo.find("Riverton")
    assert ids(found) == ["town:riverton", "geonames:5"]
    assert [e.country for e in found] == ["XA", "XB"]
    assert found[0].score > found[1].score


def test_admin1_filter_and_strict_false(geo):
    assert ids(geo.find("Riverton", admin1="XB-W")) == ["geonames:5"]
    assert ids(geo.find("Riverton", state="XB-W", strict=False)) == ["geonames:5", "town:riverton"]


def test_near_boost_and_radius_filter(geo):
    assert geo.find("Riverton", near=(0.5, -138.7))[0].place.id == "geonames:5"
    assert ids(geo.find("Riverton", near=(0.22, -139.27), radius_km=20)) == ["town:riverton"]


def test_bbox_and_within(geo):
    assert ids(geo.find("Riverton", bbox=(0.4, -139.0, 0.6, -138.5))) == ["geonames:5"]
    assert ids(geo.find("Riverton", within="South Province")) == ["town:riverton"]
    assert ids(geo.find("Riverton", within="iso:XB-W")) == ["geonames:5"]
    with pytest.raises(ValueError, match="within"):
        geo.find("Riverton", within="Nowhere At All")


def test_kinds_filter_accepts_everyday_words(geo):
    assert ids(geo.find("Alpha City", kinds="metro")) == ["metro:alpha-city"]
    assert ids(geo.find("Alpha Falls", kinds=["park"])) == ["parks:ALFA"]
    assert geo.find("Alpha Falls", kinds="lake") == []
    with pytest.raises(ValueError, match="kind"):
        geo.find("Alpha Falls", kinds="volcano-ish")


def test_park_outline_and_point_merge(geo):
    found = geo.find("Alpha Falls National Park")
    assert ids(found) == ["parks:ALFA"]
    assert [p.id for p in found[0].alternates] == ["wikidata:Q900001"]
    assert found[0].place.tier == 1 and found[0].place.aliases == ("Alpha Falls",)
    assert found[0].region == "South Province"


def test_aliases_and_codes(geo):
    assert geo.find("Alpha Falls")[0].place.id == "parks:ALFA"
    assert geo.find("ALFA")[0].place.id == "parks:ALFA"
    assert geo.find("XA")[0].place.kind is PlaceKind.COUNTRY
    assert geo.find("XA-N")[0].place.id == "iso:XA-N"


def test_airport_code_means_the_city_it_serves_then_the_airport(geo):
    found = geo.find("XAI")
    assert ids(found)[:2] == ["town:alpha-city", "ourairports:XAAA"]
    assert geo.find("XAAA")[0].place.id == "town:alpha-city"
    assert geo.find("XAI", kinds="airport")[0].place.id == "ourairports:XAAA"
    airport = geo.find("XAI airport")[0]
    assert airport.place.id == "ourairports:XAAA" and airport.place.codes["iata"] == "XAI"
    assert airport.city == "Alpha City"  # an airport carries the city it is in


def test_typos_and_prefixes(geo):
    assert geo.find("Alpha Citty")[0].place.id == "town:alpha-city"
    assert geo.find("Rivertn")[0].place.id == "town:riverton"
    assert "parks:ALFA" in ids(geo.find("Alpha F", prefix=True))
    assert geo.find("Rivert", prefix=True)[0].place.id == "town:riverton"


def test_get_by_id_and_geometry(geo):
    park = geo.get("parks:ALFA")
    assert park.place.name == "Alpha Falls National Park" and park.outline is None
    with_outline = geo.get("parks:ALFA", geometry=True)
    s, w, n, e = PARK_BOX
    assert with_outline.contains((s + n) / 2, (w + e) / 2) and not with_outline.contains(n + 0.1, w)
    assert geo.find("parks:ALFA")[0].place.id == "parks:ALFA"
    assert geo.get("wikidata:Q900001").place.id == "wikidata:Q900001"
    with pytest.raises(KeyError):
        geo.get("parks:NOPE")


def test_coordinates_as_text(geo):
    top = geo.find("0.75, -139.5")
    assert len(top) == 1
    assert top[0].place.id == "geo:0.750000,-139.500000" and top[0].region == "North Province"
    assert geo.get("geo:0.75,-139.5").point.lat == 0.75


def test_limit(geo):
    assert len(geo.find("Riverton", limit=1)) == 1
    assert geo.find("Riverton", limit=0) == []


def test_bad_arguments(geo):
    with pytest.raises(ValueError, match="empty"):
        geo.find("  ")
    with pytest.raises(ValueError, match="radius_km"):
        geo.find("Riverton", radius_km=5)
    with pytest.raises(ValueError, match="admin1"):
        geo.find("Riverton", admin1="Nowhere Province")


def test_overrides_alias_rename_hide_and_add(tmp_path):
    rules = {
        "alias": [{"text": "The Big A", "means": "town:alpha-city"}],
        "rename": [{"id": "lake:alpha", "name": "Alpha Water", "aliases": ["Big Pond"]}],
        "hide": [{"id": "geonames:5"}],
        "add": [
            {"kind": "custom", "name": "Alpha Pier", "point": {"lat": 0.79, "lon": -139.41}, "id": "app:pier"}
        ],
    }
    geo = geocoder(tmp_path, overrides=OverrideEngine.from_documents([(Layer.APP, rules, "app")]))
    assert geo.find("The Big A")[0].place.id == "town:alpha-city"
    lake = geo.find("Alpha Water")[0]
    assert lake.place.id == "lake:alpha" and lake.place.name == "Alpha Water"
    assert "Lake Alpha" in lake.place.aliases
    assert geo.find("Lake Alpha")[0].place.name == "Alpha Water"
    assert ids(geo.find("Riverton")) == ["town:riverton"]
    with pytest.raises(KeyError):
        geo.get("geonames:5")
    pier = geo.find("Alpha Pier")[0]
    assert pier.place.id == "app:pier" and pier.contains(0.79, -139.41)
    assert geo.get("app:pier").place.name == "Alpha Pier"


def test_a_word_that_names_nothing_reads_as_a_prefix(geo):
    # "Lake" is no place's whole name, but within a region and kind it means the lakes there
    assert ids(geo.find("Lake", kinds="water")) == ["lake:alpha"]
    assert ids(geo.find("Lake", within="South Province", kinds="water")) == ["lake:alpha"]
    assert geo.find("Lake", within="North Province", kinds="water") == []
