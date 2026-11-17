"""world.subregions and world.subregion: ISO 3166-2 subdivisions for the countries with tables."""

from collections import Counter

import pytest

from placewise import world
from placewise.model import Subregion


def test_us_has_50_states_dc_and_the_territories():
    us = world.subregions("US")
    assert all(isinstance(s, Subregion) and s.country == "US" for s in us)
    kinds = Counter(s.kind for s in us)
    assert kinds == {"state": 50, "district": 1, "territory": 5}
    ca_state = next(s for s in us if s.short_code == "CA")
    assert (ca_state.code, ca_state.name, ca_state.codes) == ("US-CA", "California", {"fips": "06"})
    assert [s.code for s in world.subregions("usa", kind="territory")] == [
        "US-AS",
        "US-GU",
        "US-MP",
        "US-PR",
        "US-VI",
    ]


def test_canada_india_and_the_uk():
    assert Counter(s.kind for s in world.subregions("Canada")) == {"province": 10, "territory": 3}
    assert world.subregions("CA", kind="territory")[0].codes == {"sgc": "60"}
    india = Counter(s.kind for s in world.subregions("IN"))
    assert india == {"state": 28, "union territory": 8}
    uk = {s.code: s.kind for s in world.subregions("GB")}
    assert uk == {"GB-ENG": "country", "GB-SCT": "country", "GB-WLS": "country", "GB-NIR": "province"}


def test_countries_without_a_table_raise_lookup_error():
    with pytest.raises(LookupError, match="not available yet") as info:
        world.subregions("FR")
    assert "France" in str(info.value) and not isinstance(info.value, KeyError)


def test_bad_kind_is_an_error():
    with pytest.raises(ValueError, match="county"):
        world.subregions("US", kind="county")


@pytest.mark.parametrize(
    ("given", "country", "code"),
    [
        ("CA-ON", None, "CA-ON"),
        ("ca-on", None, "CA-ON"),
        ("Ontario", None, "CA-ON"),
        ("ON", "CA", "CA-ON"),
        ("ON", "Canada", "CA-ON"),
        ("Ont.", None, "CA-ON"),
        ("CA", "US", "US-CA"),
        ("California", None, "US-CA"),
        ("Orissa", None, "IN-OD"),  # former name
        ("OR", "IN", "IN-OD"),  # replaced code
        ("Wales", None, "GB-WLS"),
    ],
)
def test_subregion_by_code_or_name(given, country, code):
    assert world.subregion(given, country=country).code == code


def test_subregion_errors():
    with pytest.raises(KeyError, match="AR") as info:
        world.subregion("AR")  # Arkansas and Arunachal Pradesh
    assert "US-AR" in str(info.value) and "IN-AR" in str(info.value)
    with pytest.raises(KeyError, match="Ontaria") as info:
        world.subregion("Ontaria")
    assert "Ontario" in str(info.value)
    with pytest.raises(KeyError):
        world.subregion("ON", country="US")
    with pytest.raises(LookupError, match="not available yet"):
        world.subregion("FR-75")
