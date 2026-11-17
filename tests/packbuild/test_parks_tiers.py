"""Tier crosswalks and the name and id rules of the park sources (packbuild.sources.parks.tiers)."""

import pytest

from packbuild.sources.parks import tiers
from placewise.constants.parks import LOCAL, NATIONAL, REGIONAL, STATE, TIERS


def test_every_crosswalk_names_a_known_tier():
    assert {t for t, _ in tiers.NPS_TYPES.values()} <= set(TIERS)
    assert {t for t, _ in tiers.PADUS_TYPES.values()} <= set(TIERS)
    assert set(tiers.CPCAD_TYPES.values()) <= set(TIERS)
    assert set(tiers.WIKIDATA_CLASSES.values()) <= set(TIERS)


def test_flagships_are_national_and_city_parks_local():
    assert tiers.NPS_TYPES["National Parks"] == (NATIONAL, "National Park")
    assert tiers.CPCAD_TYPES["National Urban Park"] == NATIONAL  # Rouge
    assert tiers.CPCAD_TYPES["Provincial Park"] == STATE and tiers.PADUS_TYPES["SP"][0] == STATE
    assert tiers.CPCAD_TYPES["Conservation Reserve"] == REGIONAL
    assert tiers.PADUS_TYPES["LP"] == (LOCAL, "Local Park")
    # private, NGO and habitat designations aren't parks
    for dropped in (
        "Privately Protected Area",
        "Water fowl gathering area",
        "White-tailed deer yard",
        "OECM",
    ):
        assert dropped not in tiers.CPCAD_TYPES
    assert "PCON" not in tiers.PADUS_TYPES and "TRIBL" not in tiers.PADUS_TYPES


@pytest.mark.parametrize(
    ("name", "usable"),
    [("Central Park", True), ("Yosemite National Park", True), ("", False), ("Unknown", False),
     ("BLM 123", False), ("Tax#0313-05-2531", False), ("City of Newport", False), ("Town Forest", True)],
)  # fmt: skip
def test_usable_names(name, usable):
    assert tiers.usable_name(name) is usable


def test_cpcad_names_lose_their_suffixes():
    assert tiers.cpcad_name("Banff National Park Of Canada") == (
        "Banff National Park", "Banff National Park of Canada"
    )  # fmt: skip
    assert tiers.cpcad_name("Algonquin Provincial Park (Natural Environment Class)") == (
        "Algonquin Provincial Park", ""
    )  # fmt: skip
    assert tiers.cpcad_name("  Rouge National   Urban Park ") == ("Rouge National Urban Park", "")


def test_short_names_slugs_and_name_tiers():
    assert tiers.short_name("Yosemite National Park", "National Park") == "Yosemite"
    assert tiers.short_name("National Park", "National Park") == ""
    assert tiers.short_name("Central Park", "Local Park") == ""
    assert tiers.slug("Parc national du Mont-Mégantic") == "parc-national-du-mont-megantic"
    assert tiers.name_tier("Kaziranga National Park") == NATIONAL
    assert tiers.name_tier("Corbett Tiger Reserve") == NATIONAL
    assert tiers.name_tier("Bhimashankar Wildlife Sanctuary") == STATE
    assert tiers.name_tier("Sundarbans") is None
