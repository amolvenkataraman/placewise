"""India pack features flagged `india_view_only` (ground only India's view puts in India) answer
only when the IN view decided the country. Synthetic boxes in open Pacific water; "XO" and its
strip are invented.

lon -148 ........ -147.5 ......... -147 | -147 ......... -146
lat 11   India: PIN 560066 (view only)  | Otherland (XO)
                                        |  Claimed Strip (lat 10.4 - 10.6, lon -147 .. -146.8):
lat 10   India: PIN 110001              |  held by XO, India's view: India; PIN 560067 (view only)
"""

import numpy as np
import pytest
from naming_kit import CREATED, VERSION, polygons

from placewise.engine import Geocoder
from placewise.packs import LayerData, write_pack

STRIP = (10.5, -146.9)
VIEW_ONLY_IN_INDIA = (10.8, -147.25)
PLAIN = (10.2, -147.25)


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
            ((10, -148, 10.5, -147), "iso:IN-DL", "Delhi", "IN", "IND"),
            ((10.5, -148, 11, -147), "iso:IN-KA", "Karnataka", "IN", "IND"),
            ((10, -147, 11, -146), "iso:XO-01", "Other Province", "XO", "XOO"),
        ],
        ("id", "name", "country", "adm0_a3"),
    )
    areas = polygons(
        "worldviews",
        [((10.4, -147, 10.6, -146.8), "ne:1", "Claimed Strip", "XOO", "IND")],
        ("id", "name", "adm0_a3", "adm0_a3_in"),
    )
    cities = LayerData(
        "cities", "point",
        {"id": ["geonames:1", "geonames:2"], "name": ["Delhi", "Other Town"], "country": ["IN", "XO"],
         "population": np.array([1_000_000, 50_000], dtype=np.int64), "feature_code": ["PPLA", "PPLA"],
         "timezone": ["Asia/Kolkata", "Pacific/Test"]},
        ("synthetic",), lat=np.array([10.2, 10.5]), lon=np.array([-147.8, -146.5]),
    )  # fmt: skip
    return write_pack(out / "world", "world", VERSION, [countries, admin1, areas, cities], created=CREATED)


def _india(out):
    rows = [
        ((10, -148, 10.5, -147), "pin:110001", "New Delhi GPO", "110001", "NEW DELHI", "IN-DL", ""),
        ((10.5, -148, 11, -147), "pin:560066", "Whitefield S.O", "560066", "BENGALURU URBAN", "IN-KA", "1"),
        ((10.4, -147, 10.6, -146.8), "pin:560067", "Strip S.O", "560067", "BENGALURU URBAN", "IN-KA", "1"),
    ]
    columns = ("id", "name", "pincode", "district", "state_code", "india_view_only")
    pincodes = polygons("pincodes", rows, columns)
    return write_pack(out / "in", "in", VERSION, [pincodes], created=CREATED)


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    out = tmp_path_factory.mktemp("ind-worldview")
    return Geocoder(packs=[_world(out), _india(out)])


def test_view_only_pin_areas_stay_silent_in_the_de_facto_view(geo):
    r = geo.lookup(*STRIP)
    assert r.country.id == "iso:XO" and r.postal is None
    r = geo.lookup(*VIEW_ONLY_IN_INDIA)
    assert r.country.id == "iso:IN" and r.postal is None
    assert r.admin1.id == "iso:IN-KA" and r.sources["admin1"] == "world/admin1:polygon"
    assert geo.lookup(*PLAIN).postal.name == "110001"  # unflagged PIN areas answer as usual


def test_view_only_pin_areas_answer_in_the_india_view(geo):
    r = geo.lookup(*STRIP, worldview=("IN", "de_facto"))
    assert r.country.id == "iso:IN" and r.postal.name == "560067"
    assert r.admin1.id == "iso:IN-KA" and r.sources["admin1"] == "in/pincodes:state"
    assert geo.lookup(*VIEW_ONLY_IN_INDIA, worldview=("IN",)).postal.name == "560066"
