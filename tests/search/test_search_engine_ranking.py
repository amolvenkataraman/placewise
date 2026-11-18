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
]
# places of the extra pack: (id, name, aliases, abbreviations, kind, rank, lat, lon)
EXTRA = [
    ("extra:river", "Alpha", "", "", "water", 0.7, 0.55, -139.45),
    ("extra:river-park", "Alpha River", "", "", "park", 0.5, 0.56, -139.46),
    ("extra:forest", "Beta Town National Forest", "Beta Town", "", "park", 0.95, 0.3, -138.9),
    ("extra:xai", "Xai", "", "", "locality", 0.6, 0.1, -139.9),
    ("extra:zone", "Zeta Zone", "", "XAI", "region", 0.6, 0.9, -138.6),
    ("extra:zip", "11111", "", "", "postal_code", 0.2, 0.26, -138.97),
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


def _extra(tmp_path):
    layer = LayerData(
        "things",
        "point",
        {"id": [r[0] for r in EXTRA], "name": [r[1] for r in EXTRA]},
        ("synthetic",),
        lat=np.array([r[6] for r in EXTRA]),
        lon=np.array([r[7] for r in EXTRA]),
    )
    rows = []
    for i, (ident, name, alias, abbreviation, kind, rank, *_) in enumerate(EXTRA):
        rows.append((name, "things", i, kind, rank, "code" if kind == "postal_code" else "official"))
        rows.append((ident, "things", i, kind, rank, "code"))
        if alias:
            rows.append((alias, "things", i, kind, rank, "alias"))
        if abbreviation:
            rows.append((abbreviation, "things", i, kind, rank, "abbreviation"))
    pack = open_pack(
        write_pack(tmp_path, "extra", "2026.11", [layer], created=CREATED, names=NameData.from_rows(rows))
    )
    if _real_index(pack) is None:
        pack.__dict__["names"] = FakeNameIndex(pack, rows)
    return pack


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ranking")
    return Geocoder(packs=[*write_packs(tmp), _notable(tmp), _extra(tmp)])


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
