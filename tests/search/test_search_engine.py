"""Forward search on the synthetic world (search_kit): ranking, merging, context, codes, ids."""

import pytest
from search_kit import ALPHA_CITY_BOX, PARK_BOX, geocoder, write_packs

from placewise.constants.search import CONTEXT_BORDER_KM as BORDER_KM
from placewise.engine import Geocoder
from placewise.model import Entity, Layer, Match, PlaceKind, Relation
from placewise.overrides import OverrideEngine
from placewise.packs import NameData, open_pack, write_pack
from tests.engine.postal_kit import postal_layer

WITHIN = Match(Relation.WITHIN, 0.0)


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


def test_a_trailing_city_word_reads_as_the_comma_context(tmp_path):
    import numpy as np
    from search_kit import write_packs

    from packbuild import names
    from placewise.engine import Geocoder
    from placewise.packs import LayerData, write_pack

    # two famous piers of one name: the better known by Beta Town, the other by Tinyville
    layer = LayerData(
        "notable", "point",
        {"id": ["wikidata:Q901", "wikidata:Q902"], "name": ["Union Pier", "Union Pier"], "aliases": ["", ""],
         "kind": ["landmark", "landmark"], "fame": np.array([0.7, 0.65], dtype=np.float32)},
        ("synthetic",), lat=np.array([0.26, 0.76]), lon=np.array([-138.96, -139.36]),
    )  # fmt: skip
    notable = write_pack(
        tmp_path, "world-notable", "2026.11", [layer], names=names.for_pack("world-notable", [layer])
    )
    geo = Geocoder(packs=[*write_packs(tmp_path), notable])
    assert ids(geo.find("Union Pier"))[0] == "wikidata:Q901"
    # no place is called "Union Pier Tinyville": it reads as "Union Pier, Tinyville"
    assert ids(geo.find("Union Pier Tinyville"))[0] == "wikidata:Q902"
    assert ids(geo.find("Union Pier, Tinyville"))[0] == "wikidata:Q902"


def test_generic_park_names_are_never_found(tmp_path):
    """Packs built before the park build dropped them still index "Open Space" rows."""
    import numpy as np
    from search_kit import CREATED, FakeNameIndex, _real_index, box_feature, world_layers, world_names

    from placewise.engine import Geocoder
    from placewise.packs import LayerData, NameData, open_pack, write_pack

    columns = {
        "id": ["pad-us:a", "pad-us:b"],
        "park": ["pad-us:a", "pad-us:b"],
        "name": ["Open Space", "Willow Park"],
        "tier": np.array([4, 4], dtype=np.uint8),
    }
    boxes = [box_feature(0.30, -139.9, 0.31, -139.89), box_feature(0.32, -139.9, 0.33, -139.89)]
    parks = LayerData("parks_local", "polygon", columns, ("synthetic",), features=boxes)
    rows = [
        ("Open Space", "parks_local", 0, "park", 0.5, "official"),
        ("Willow Park", "parks_local", 1, "park", 0.5, "official"),
    ]
    packs = []
    for name, layers, names in (("world", world_layers(), None), ("usa-parks", [parks], rows)):
        names = names if names is not None else world_names(layers)
        path = write_pack(tmp_path, name, "2026.11", layers, created=CREATED, names=NameData.from_rows(names))
        pack = open_pack(path)
        if _real_index(pack) is None:
            pack.__dict__["names"] = FakeNameIndex(pack, names)
        packs.append(pack)
    geo = Geocoder(packs=packs)
    assert ids(geo.find("Willow Park")) == ["pad-us:b"]
    assert "pad-us:a" not in ids(geo.find("Open Space"))
    assert "pad-us:a" not in ids(geo.find("Open Space", prefix=True))


def test_a_place_just_offshore_is_in_the_country_and_region_its_coast_is(geo):
    # Seaview's point is 5.6 km off Alphaland's coast: within its territorial sea, as lookup has it
    port = geo.find("Seaview")[0]
    full = geo.lookup(port.point.lat, port.point.lon)
    assert full.cc == "XA" and full.admin1.name == "North Province"
    assert (port.country, port.region) == ("XA", "North Province")
    assert port.place.codes["iso2"] == "XA" and port.place.codes["admin1"] == "N"
    assert ids(geo.find("Seaview", admin1="XA-N")) == ["geonames:6"]
    assert ids(geo.find("Seaview, North Province")) == ["geonames:6"]
    # far out at sea, it is in no country
    reef = geo.find("Farout Reef")[0]
    assert (reef.country, reef.region) == (None, None)
    assert geo.find("Farout Reef", admin1="XA-N") == []


# -- how sure the context is ------------------------------------------------------------------------


def test_context_inside_both_polygons_far_from_a_border_is_certain(geo):
    top = geo.find("Alpha City")[0]
    assert top.context_matches == {"country": WITHIN, "region": WITHIN}
    assert top.context_certain is True


def test_context_snapped_from_offshore_is_not_certain(geo):
    port = geo.find("Seaview")[0]  # 5.6 km off the coast: country and region by the territorial sea
    assert (port.country, port.region) == ("XA", "North Province")
    assert set(port.context_matches) == {"country", "region"}
    assert {m.relation for m in port.context_matches.values()} == {Relation.OFFSHORE}
    assert all(m.distance_km is not None and m.distance_km > 0 for m in port.context_matches.values())
    assert port.context_certain is False


def test_context_near_a_border_is_not_certain(geo):
    # Beta Town is 3.3 km from the Alphaland border: inside both polygons, but a coarse outline
    # can put a place this close on the wrong side
    town = geo.find("Beta Town")[0]
    assert (town.country, town.region) == ("XB", "West Region")
    assert town.context_matches == {"country": WITHIN, "region": WITHIN}
    assert BORDER_KM > 3.4
    assert town.context_certain is False


def test_no_context_claims_nothing(geo):
    reef = geo.find("Farout Reef")[0]
    assert reef.country is None and reef.context_matches == {}
    assert reef.context_certain is True


def test_context_from_a_full_lookup_carries_the_city_match(geo):
    airport = geo.find("XAI airport")[0]  # airports carry a city: their context is a full lookup
    full = geo.lookup(airport.point.lat, airport.point.lon)
    assert airport.context_matches["city"] == full.matches["city"]
    assert airport.context_matches["country"] == full.matches["country"] == WITHIN
    assert airport.context_matches["region"] == full.matches["admin1"] == WITHIN
    assert airport.context_certain is True  # a nearest city doesn't make the country or region unsure


def test_coordinates_typed_as_text_carry_how_sure_their_context_is(geo):
    sure, unsure = geo.find("0.75, -139.5")[0], geo.find("0.25, -138.97")[0]
    assert sure.context_certain is True and sure.context_matches["country"] == WITHIN
    assert unsure.country == "XB" and unsure.context_certain is False


def test_context_matches_survive_the_dict_round_trip(geo):
    port = geo.find("Seaview")[0]
    data = port.to_dict()
    assert data["context_certain"] is False and data["context_matches"]["country"]["relation"] == "offshore"
    assert Entity.from_dict(data) == port


# a GB-style outward code and a code written with a space, as the world-postal pack indexes them
_POSTCODES = [
    ("postal:XA:AB1", "AB1", "Alpha City", "XA", 0.75, -139.5, 10.0, False),
    ("postal:XB:10000", "100 00", "Beta Town", "XB", 0.25, -138.97, 10.0, False),
]


@pytest.fixture(scope="module")
def postal_geo(tmp_path_factory):
    root = tmp_path_factory.mktemp("search-postal")
    rows = [("AB1", "postal", 0, "postal_code", 0.2, "code")]
    rows += [(code, "postal", 1, "postal_code", 0.2, "code") for code in ("100 00", "10000")]
    path = write_pack(
        root, "world-postal", "2026.11", [postal_layer(_POSTCODES)], names=NameData.from_rows(rows)
    )
    return Geocoder(packs=[*write_packs(root), open_pack(path)])


@pytest.mark.parametrize(
    ("text", "ident"),
    [
        ("AB1", "postal:XA:AB1"),
        ("AB1 2CD", "postal:XA:AB1"),  # a full UK postcode finds its outward code
        ("100 00", "postal:XB:10000"),
        ("10000", "postal:XB:10000"),
    ],
)
def test_postcodes_with_and_without_their_space(postal_geo, text, ident):
    found = postal_geo.find(text)
    assert ids(found)[:1] == [ident] and found[0].place.kind is PlaceKind.POSTAL_CODE


def test_a_postcodes_first_part_is_tried_only_when_the_whole_code_matches_nothing(postal_geo):
    assert postal_geo.find("XY9 9ZZ") == []
