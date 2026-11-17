"""Several places in one string, and the separators between and within them."""

import pytest

from placewise.text import parse_location


def places(parsed):
    """(city, admin1, country) of each primary part."""
    return [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts]


# --- Separators ---------------------------------------------------------------------------------

TWO_CITIES = [("Toronto", "ON", "CA"), ("Vancouver", "BC", "CA")]


@pytest.mark.parametrize(
    "text",
    [
        "Toronto, ON; Vancouver, BC",
        "Toronto, ON | Vancouver, BC",
        "Toronto, ON / Vancouver, BC",
        "Toronto, ON or Vancouver, BC",
        "Toronto, ON and Vancouver, BC",
        "Toronto, ON & Vancouver, BC",
        "Toronto, ON, Vancouver, BC",
        "Toronto, ON\nVancouver, BC",
        "Toronto (ON) or Vancouver (BC)",
        "Toronto, Ontario • Vancouver, British Columbia",
    ],
)
def test_place_separators(text):
    parsed = parse_location(text)
    assert places(parsed) == TWO_CITIES
    assert parsed.multiple


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Austin, TX", ("Austin", "TX", "US")),
        ("Austin - TX", ("Austin", "TX", "US")),
        ("Austin TX", ("Austin", "TX", "US")),
        ("Austin,TX", ("Austin", "TX", "US")),
        ("Austin, Texas, USA", ("Austin", "TX", "US")),
        ("Austin TX USA", ("Austin", "TX", "US")),
        ("US-TX-Austin", ("Austin", "TX", "US")),
        ("USA - TX - Austin", ("Austin", "TX", "US")),
        ("Texas - Austin", ("Austin", "TX", "US")),
        ("US, TX, Austin", ("Austin", "TX", "US")),
        ("Austin (TX)", ("Austin", "TX", "US")),
        ("Somerville-MA", ("Somerville", "MA", "US")),
        ("Ottawa Canada", ("Ottawa", "ON", "CA")),
        ("Toronto Ontario", ("Toronto", "ON", "CA")),
        ("Durham North Carolina", ("Durham", "NC", "US")),
    ],
)
def test_hierarchy_separators_and_orders(text, expected):
    assert places(parse_location(text)) == [expected]


@pytest.mark.parametrize("text", ["Wilkes-Barre, PA", "Winston-Salem, NC", "Stoke-on-Trent, UK"])
def test_hyphenated_city_names_stay_whole(text):
    city = parse_location(text).parts[0].city
    assert city == text.split(",")[0]


# --- Multi-location -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Multiple Locations", []),
        ("Various locations", []),
        ("Multiple Locations, GB", [(None, None, "GB")]),
        ("Seattle, WA + 6 others", [("Seattle", "WA", "US")]),
        ("San Francisco, CA +2 more", [("San Francisco", "CA", "US")]),
        ("Mountain View, CA +29", [("Mountain View", "CA", "US")]),
        ("Toronto, ON, Canada and 3 more locations", [("Toronto", "ON", "CA")]),
        ("3 Locations", []),
        (
            "Austin, Dallas, Houston",
            [("Austin", None, None), ("Dallas", None, None), ("Houston", None, None)],
        ),
        ("Canada; United States", [(None, None, "CA"), (None, None, "US")]),
    ],
)
def test_multiple(text, expected):
    parsed = parse_location(text)
    assert parsed.multiple
    assert places(parsed) == expected


def test_one_place_given_twice_is_one_part():
    parsed = parse_location("NYC; New York, NY")
    assert places(parsed) == [("New York City", "NY", "US")]
    assert parsed.parts[0].region == "NYC"
    assert not parsed.multiple
