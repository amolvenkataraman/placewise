"""The country groups location search reads as remote-scope regions ("Remote - EMEA"), taken from
the country-group tables (constants.countries.groups); no table of its own."""

import pytest

from placewise.constants import countries
from placewise.constants.countries import groups
from placewise.constants.location_text import REMOTE_SCOPE_GROUPS, WORLDWIDE_GROUP
from placewise.text import is_remote_ok_for, parse_location
from placewise.text import regions as scope


def test_every_scope_group_is_a_known_group():
    known = {**groups.GEOGRAPHIC, **groups.LEGAL}
    assert set(REMOTE_SCOPE_GROUPS) <= set(known) and WORLDWIDE_GROUP in REMOTE_SCOPE_GROUPS


def test_regions_use_real_country_codes():
    for region in scope.all_regions():
        assert region.members is None or region.members <= set(countries.BY_ALPHA2), region.name


@pytest.mark.parametrize(
    ("name", "group_name"),
    [
        ("EU", "European Union"),
        ("European Union", "European Union"),
        ("EMEA", "EMEA"),
        ("Asia Pacific", "APAC"),
        ("Asia Pac", "APAC"),
        ("North America", "North America"),
        ("NORAM", "NA / NAMER"),
        ("AMER", "Americas (UN M49)"),
        ("Nordics", "Nordic countries"),
        ("Worldwide", "World"),
        ("Anywhere", "World"),
    ],
)
def test_names_find_their_group(name, group_name):
    assert scope.find(name).name == group_name


def test_eu_is_the_current_27_and_worldwide_has_no_limit():
    eu = scope.find("EU")
    assert len(eu.members) == 27 and "GB" not in eu.members
    assert scope.find("Worldwide").members is None and scope.find("Worldwide").contains("FR")
    assert "CA" in scope.find("North America").members


def test_groups_location_search_does_not_read_as_a_scope():
    # "US & Canada" stays two countries, so a remote listing there is limited to US and CA
    assert scope.find("US & Canada") is None
    assert scope.find("NATO") is None


@pytest.mark.parametrize(
    ("text", "country", "keep"),
    [
        ("Remote - EU", "FR", True),
        ("Remote - EU", "GB", False),
        ("Remote - EU", "NO", False),
        ("Remote - EMEA", "ZA", True),
        ("Remote - US & Canada", "CA", True),
        ("Remote - US & Canada", "MX", False),
    ],
)
def test_remote_scope_through_the_groups(text, country, keep):
    assert is_remote_ok_for(parse_location(text), country).keep is keep


def test_us_and_canada_stays_two_countries():
    assert parse_location("Remote - US & Canada").remote_scope == ("US", "CA")
    assert parse_location("Remote - EU").remote_scope == ("European Union",)
