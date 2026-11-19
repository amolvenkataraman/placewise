"""Search ranking on the synthetic world (search_kit) plus a few namesakes: what is named after a
place comes after it, codes read as words, postal codes, rivers known without the word."""

import numpy as np
import pytest
from search_kit import CREATED, FakeNameIndex, _real_index, write_packs

from packbuild import names
from placewise.engine import Geocoder
from placewise.packs import LayerData, NameData, open_pack, write_pack

# famous things named after the kit's cities: Beta Town (500k people) and Riverton
NOTABLE = [
    # id, name, aliases, kind, fame, station code, lat, lon
    ("wikidata:Q911", "Beta Town", "", "station", 1.0, "11111", 0.25, -138.96),
    ("wikidata:Q912", "University of Beta", "Beta Town", "university", 1.0, "", 0.26, -138.95),
    ("wikidata:Q913", "Beta Tower", "", "landmark", 1.0, "", 0.24, -138.97),
    # an airport known by its name without the words "International Airport", a station named
    # after it, and an airport named after a city
    ("wikidata:Q914", "Gamma International Airport", "", "airport", 1.0, "", 0.6, -139.2),
    ("wikidata:Q915", "Gamma", "", "station", 0.8, "", 0.61, -139.2),
    ("wikidata:Q916", "Beta Town Airport", "", "airport", 1.0, "", 0.27, -138.9),
    ("wikidata:Q917", "Delta Airport", "", "airport", 1.0, "", 0.45, -139.6),
    # a famous landmark known as Barabar Hill, two letters from a neighbourhood's name
    ("wikidata:Q918", "Barabar Caves", "Barabar Hill", "landmark", 1.0, "", 0.85, -138.7),
    ("wikidata:Q919", "Epsilon International Airport", "", "airport", 1.0, "", 0.9, -139.9),
]
# places of the extra pack: (id, name, aliases, abbreviations, kind, rank, lat, lon)
EXTRA = [
    ("extra:river", "Alpha", "", "", "water", 0.7, 0.55, -139.45),
    ("extra:river-park", "Alpha River", "", "", "park", 0.5, 0.56, -139.46),
    ("extra:forest", "Beta Town National Forest", "Beta Town", "", "park", 0.95, 0.3, -138.9),
    ("extra:xai", "Xai", "", "", "locality", 0.6, 0.1, -139.9),
    ("extra:zone", "Zeta Zone", "", "XAI", "region", 0.6, 0.9, -138.6),
    ("extra:zip", "11111", "", "", "postal_code", 0.2, 0.26, -138.97),
    # a province the world pack ranks low and abbreviates IPR, and a town called Ipr
    ("extra:isle", "Isle Province", "", "IPR", "admin1", 0.5, 0.62, -139.1),
    ("extra:ipr", "Ipr", "", "", "locality", 0.55, 0.05, -139.0),
    # a neighbourhood (ranked low, as India Post's are) beside an airport named after it
    ("extra:delta", "Delta", "", "", "sublocality", 0.2, 0.46, -139.6),
    ("extra:kalabar", "Kalabar Hill", "", "", "sublocality", 0.2, 0.47, -139.6),
    ("extra:epsilon", "Epsilon", "", "", "locality", 0.1, 0.1, -138.6),  # a hamlet far from it
]
# a country pack: the same province, ranked as its country ranks its provinces, and a province of
# the same name elsewhere
COUNTRY = [
    ("land:isle", "Isle Province", "", "", "admin1", 0.8, 0.621, -139.1),
    ("land:other-isle", "Isle Province", "", "", "admin1", 0.9, 0.1, -138.5),
]


def _notable(tmp_path):
    columns = {
        "id": [r[0] for r in NOTABLE],
        "name": [r[1] for r in NOTABLE],
        "aliases": [r[2] for r in NOTABLE],
        "kind": [r[3] for r in NOTABLE],
        "fame": np.array([r[4] for r in NOTABLE], dtype=np.float32),
        "station_code": [r[5] for r in NOTABLE],
    }
    layer = LayerData(
        "notable",
        "point",
        columns,
        ("synthetic",),
        lat=np.array([r[6] for r in NOTABLE]),
        lon=np.array([r[7] for r in NOTABLE]),
    )
    return open_pack(
        write_pack(
            tmp_path, "world-notable", "2026.11", [layer], names=names.for_pack("world-notable", [layer])
        )
    )


def _extra(tmp_path, name="extra", places=EXTRA):
    layer = LayerData(
        "things",
        "point",
        {"id": [r[0] for r in places], "name": [r[1] for r in places]},
        ("synthetic",),
        lat=np.array([r[6] for r in places]),
        lon=np.array([r[7] for r in places]),
    )
    rows = []
    for i, (ident, label, alias, abbreviation, kind, rank, *_) in enumerate(places):
        rows.append((label, "things", i, kind, rank, "code" if kind == "postal_code" else "official"))
        rows.append((ident, "things", i, kind, rank, "code"))
        if alias:
            rows.append((alias, "things", i, kind, rank, "alias"))
        if abbreviation:
            rows.append((abbreviation, "things", i, kind, rank, "abbreviation"))
    pack = open_pack(
        write_pack(tmp_path, name, "2026.11", [layer], created=CREATED, names=NameData.from_rows(rows))
    )
    if _real_index(pack) is None:
        pack.__dict__["names"] = FakeNameIndex(pack, rows)
    return pack


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ranking")
    return Geocoder(packs=[*write_packs(tmp), _notable(tmp), _extra(tmp), _extra(tmp, "land", COUNTRY)])


def ids(entities):
    return [e.place.id for e in entities]


def test_what_is_named_after_a_city_comes_after_it(geo):
    # a famous station called Beta Town, a university and a national forest known as Beta Town
    found = ids(geo.find("Beta Town"))
    assert found[0] == "geonames:3"
    assert {"wikidata:Q911", "wikidata:Q912", "extra:forest"} <= set(found[1:])


def test_a_famous_thing_of_its_own_name_stays_first(geo):
    assert ids(geo.find("Beta Tower"))[0] == "wikidata:Q913"


def test_a_code_typed_as_a_word_means_the_place_of_that_name(geo):
    # XAI is the airport's code (it serves Alpha City) and Zeta Zone's abbreviation; Xai a town
    assert ids(geo.find("Xai"))[0] == "extra:xai"
    # in capitals: the town and the zone abbreviated XAI before the airport's city
    assert ids(geo.find("XAI"))[:2] == ["extra:xai", "extra:zone"]
    assert ids(geo.find("XAAA"))[:2] == ["town:alpha-city", "ourairports:XAAA"]  # the ICAO code


def test_a_postal_code_comes_before_a_station_code(geo):
    assert ids(geo.find("11111"))[0] == "extra:zip"


def test_a_river_is_found_without_the_word(geo):
    found = ids(geo.find("Alpha River"))
    assert found[0] == "extra:river" and "extra:river-park" in found


def test_an_airport_is_found_by_its_name_without_the_words_airport(geo):
    # "Gamma": Gamma International Airport before the station named after it; a city's name
    # means the city, not an airport named after it
    assert ids(geo.find("Gamma"))[:2] == ["wikidata:Q914", "wikidata:Q915"]
    assert "wikidata:Q916" not in ids(geo.find("Beta Town"))
    # a small place: the airport at it is named after it, one elsewhere is meant by its name
    assert ids(geo.find("Delta"))[0] == "extra:delta"
    assert ids(geo.find("Epsilon"))[:2] == ["wikidata:Q919", "extra:epsilon"]


def test_a_place_known_by_an_abbreviation_ranks_as_its_best_pack_ranks_it(geo):
    # "IPR": the world pack's Isle Province (abbreviated so, ranked low) is the country pack's Isle
    # Province (ranked as provinces are), which comes before the town called Ipr; the province of
    # that name elsewhere isn't pulled in
    found = geo.find("IPR")
    assert {"extra:isle", "land:isle"} & ({found[0].place.id} | {a.id for a in found[0].alternates})
    assert "extra:ipr" in ids(found)
    assert "land:other-isle" not in ids(found)


def test_a_name_typed_exactly_lets_only_one_letter_typos_compete(geo):
    # "Kalabar Hill", a neighbourhood ranked low, before Barabar Caves (famous, known as Barabar
    # Hill: two letters off); a typo with nothing exact still finds the landmark
    assert ids(geo.find("Kalabar Hill"))[0] == "extra:kalabar"
    assert ids(geo.find("Barabar Hil"))[0] == "wikidata:Q918"
