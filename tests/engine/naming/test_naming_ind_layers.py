"""India naming over the LGD-keyed layers (states, districts, cities, neighbourhoods). Synthetic
boxes in open Pacific water; "XO" and its strip are invented, the names are public ones.

lon -148 ...... -147.5 ...... -147 | -147 ...... -146
lat 11  Haryana  | Karnataka        | Otherland (XO)
        Gurugram | Bengaluru (city: 10.7-10.9, -147.35 .. -147.15)
lat 10.5 ........| Hoskote PIN area (no city): 10.5-10.7, -147.5 .. -147.35
        Delhi (Natural Earth; the states layer puts 10.4-10.5 in Haryana)
                                   | Claimed Strip (10.4-10.6, -147 .. -146.8): XO's, India's view: Karnataka
"""

import numpy as np
import pytest
from naming_kit import CREATED, VERSION, polygons

from placewise.engine import Geocoder
from placewise.packs import LayerData, write_pack

WHITEFIELD = (10.76, -147.23)
GURUGRAM = (10.47, -147.80)  # Natural Earth's Delhi, the states layer's Haryana
HOSKOTE = (10.55, -147.42)
STRIP = (10.5, -146.9)


def _world(out):
    countries = polygons(
        "countries",
        [
            ((10, -148, 11, -147), "iso:IN", "India", "IN", "IND", "IND", "India", "IND"),
            ((10, -147, 11, -146), "iso:XO", "Otherland", "XO", "XOO", "XOO", "Otherland", "XOO"),
        ],
        ("id", "name", "iso2", "iso3", "adm0_a3", "sovereign", "adm0_a3_in"),
    )
    admin1 = polygons(
        "admin1",
        [
            ((10, -148, 10.5, -147.5), "iso:IN-DL", "Delhi", "IN", "IND"),
            ((10.5, -148, 11, -147.5), "iso:IN-HR", "Haryana", "IN", "IND"),
            ((10, -147.5, 11, -147), "iso:IN-KA", "Karnataka", "IN", "IND"),
            ((10, -147, 11, -146), "iso:XO-01", "Other Province", "XO", "XOO"),
        ],
        ("id", "name", "country", "adm0_a3"),
    )
    areas = polygons(
        "worldviews",
        [((10.4, -147, 10.6, -146.8), "ne:1", "Claimed Strip", "XOO", "IND")],
        ("id", "name", "adm0_a3", "adm0_a3_in"),
    )
    rows = [
        ("geonames:1", "Delhi", 10.2, -147.8, "IN", 11_000_000, "PPLA"),
        ("geonames:2", "Hoskote", 10.56, -147.41, "IN", 56_000, "PPL"),
        ("geonames:3", "Bengaluru", 10.8, -147.25, "IN", 8_400_000, "PPLA"),
        ("geonames:4", "Other Town", 10.5, -146.5, "XO", 50_000, "PPLA"),
    ]
    cities = LayerData(
        "cities",
        "point",
        {
            "id": [r[0] for r in rows],
            "name": [r[1] for r in rows],
            "country": [r[4] for r in rows],
            "population": np.array([r[5] for r in rows], dtype=np.int64),
            "feature_code": [r[6] for r in rows],
            "timezone": ["Asia/Kolkata"] * 3 + ["Pacific/Test"],
        },
        ("synthetic",),
        lat=np.array([r[2] for r in rows]),
        lon=np.array([r[3] for r in rows]),
    )
    return write_pack(out / "world", "world", VERSION, [countries, admin1, areas, cities], created=CREATED)


def _india(out):
    pincodes = polygons(
        "pincodes",
        [
            (
                (10.7, -147.35, 10.9, -147.15),
                "pin:560066",
                "Whitefield S.O",
                "560066",
                "BENGALURU URBAN",
                "IN-KA",
                "",
            ),
            (
                (10.5, -147.5, 10.7, -147.35),
                "pin:562114",
                "Hoskote S.O",
                "562114",
                "BENGALURU RURAL",
                "IN-KA",
                "",
            ),
            ((10.4, -147.9, 10.6, -147.7), "pin:122002", "DLF QE S.O", "122002", "GURUGRAM", "IN-HR", ""),
            ((10.4, -147, 10.6, -146.8), "pin:194401", "Strip B.O", "194401", "LEH", "IN-KA", "1"),
        ],
        ("id", "name", "pincode", "district", "state_code", "india_view_only"),
    )
    states = polygons(
        "states",
        [
            ((10.4, -148, 11, -147.5), "lgd:state:6", "Haryana", "IN-HR", "6", ""),
            ((10.5, -147.5, 11, -147), "lgd:state:29", "Karnataka", "IN-KA", "29", ""),
            ((10.4, -147, 10.6, -146.8), "lgd:state:29#india-view", "Karnataka", "IN-KA", "29", "1"),
        ],
        ("id", "name", "iso", "lgd", "india_view_only"),
    )
    districts = polygons(
        "districts",
        [
            ((10.4, -148, 11, -147.5), "lgd:district:62", "Gurugram", "IN-HR", "62", ""),
            ((10.5, -147.5, 11, -147), "lgd:district:572", "Bengaluru Urban", "IN-KA", "572", ""),
        ],
        ("id", "name", "state_code", "lgd", "india_view_only"),
    )
    cities = polygons(
        "cities",
        [
            (
                (10.7, -147.35, 10.9, -147.15),
                "lgd:ulb:276600",
                "Bengaluru",
                "IN-KA",
                "276600",
                "Municipal Corporation",
                "",
            ),
            (
                (10.45, -147.85, 10.65, -147.75),
                "lgd:ulb:248576",
                "Gurugram",
                "IN-HR",
                "248576",
                "Municipal Corporation",
                "",
            ),
        ],
        ("id", "name", "state_code", "lgd", "type", "india_view_only"),
    )
    hoods = [
        ("indiapost:560066:Whitefield S.O", "Whitefield", "lgd:ulb:276600", 10.755, -147.225),
        ("indiapost:560034:Koramangala S.O", "Koramangala", "lgd:ulb:276600", 10.85, -147.3),
        ("indiapost:562114:Kolathur S.O", "Kolathur", "lgd:ulb:999", 10.762, -147.232),  # another city's
        (
            "indiapost:560067:Tajmahal S.O",
            "Tajmahal",
            "lgd:ulb:276600",
            10.759,
            -147.229,
        ),  # another PIN area's
    ]
    neighbourhoods = LayerData(
        "neighbourhoods",
        "point",
        {
            "id": [h[0] for h in hoods],
            "name": [h[1] for h in hoods],
            "city": [h[2] for h in hoods],
            "pincode": [h[0].split(":")[1] for h in hoods],
        },
        ("synthetic",),
        lat=np.array([h[3] for h in hoods]),
        lon=np.array([h[4] for h in hoods]),
    )
    layers = [states, districts, cities, pincodes, neighbourhoods]
    return write_pack(out / "ind", "ind", VERSION, layers, created=CREATED)


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    out = tmp_path_factory.mktemp("ind-layers")
    return Geocoder(packs=[_world(out), _india(out)])


def test_a_point_in_a_city(geo):
    r = geo.lookup(*WHITEFIELD)
    assert (r.admin1.id, r.sources["admin1"]) == ("iso:IN-KA", "ind/states:polygon")
    assert (r.admin2.name, r.admin2.id, r.sources["admin2"]) == (
        "Bengaluru Urban",
        "lgd:district:572",
        "ind/districts:polygon",
    )
    assert r.admin2.type == "district"
    assert (r.locality.name, r.city.name, r.sources["city"]) == (
        "Bengaluru",
        "Bengaluru",
        "ind/cities:polygon",
    )
    assert r.locality.id == "lgd:ulb:276600"
    # the nearest neighbourhood of its own city and PIN area (Kolathur is nearer but another
    # city's, Tajmahal nearer but another PIN area's)
    assert (r.sublocality.name, r.sources["sublocality"]) == ("Whitefield", "ind/neighbourhoods:nearest")
    assert r.postal.name == "560066"


def test_the_states_layer_corrects_natural_earths_line(geo):
    r = geo.lookup(*GURUGRAM)
    assert r.admin1.id == "iso:IN-HR" and r.city.name == "Gurugram" and r.admin2.name == "Gurugram"
    assert r.label == "Gurugram, Haryana, India"


def test_outside_cities_the_city_score_names_the_place_and_the_pin_office_the_sublocality(geo):
    r = geo.lookup(*HOSKOTE)
    assert r.locality.name == "Hoskote" and r.sources["locality"] == "world/cities:score"
    assert r.admin1.id == "iso:IN-KA" and r.sublocality is None  # the office is named like the town


def test_india_view_only_units_answer_only_in_the_india_view(geo):
    r = geo.lookup(*STRIP)
    assert r.country.id == "iso:XO" and r.postal is None and r.admin2 is None
    r = geo.lookup(*STRIP, worldview=("IN",))
    assert (r.country.id, r.admin1.id, r.sources["admin1"]) == ("iso:IN", "iso:IN-KA", "ind/states:polygon")
    assert r.postal.name == "194401"
