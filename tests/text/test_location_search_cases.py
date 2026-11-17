"""Real-world location strings, as listings, profiles and feeds write them.

placewise keeps the city as written (no gazetteer yet), so where a gazetteer would rename a city
("St Paul" -> "Saint Paul") or place a bare city ("Geneva"), these cases expect the written city
and say so; the lookup layer closes that gap through the `gazetteer` hook.
"""

import pytest

from placewise.text import parse_location


def places(text, **kwargs):
    parsed = parse_location(text, **kwargs)
    return [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts]


# cities, regions and countries in the forms they come in
LOCATION_CASES = [
    ("San Francisco, CA", [("San Francisco", "CA", "US")]),
    ("SomeSmallTown, TX", [("SomeSmallTown", "TX", "US")]),
    ("US, CA, Santa Clara", [("Santa Clara", "CA", "US")]),
    ("San Francisco, CA; New York, NY", [("San Francisco", "CA", "US"), ("New York City", "NY", "US")]),
    ("NYC", [("New York City", "NY", "US")]),
    ("LA", [("Los Angeles", "CA", "US")]),
    ("SF", [("San Francisco", "CA", "US")]),
    ("United States", [(None, None, "US")]),
    ("Canada; United States", [(None, None, "CA"), (None, None, "US")]),
    ("Texas", [(None, "TX", "US")]),
    ("Nova Scotia, Canada", [(None, "NS", "CA")]),
    ("Ontario", [(None, "ON", "CA")]),
    ("Ontario, Canada", [(None, "ON", "CA")]),
    ("Ontario, CA", [("Ontario", "CA", "US")]),
    ("Ontario, OH", [("Ontario", "OH", "US")]),
    ("London, ON", [("London", "ON", "CA")]),
    ("London, UK", [("London", "ENG", "GB")]),  # admin1 from Greater London
    ("Durham, UK", [("Durham", None, "GB")]),
    ("Durham, NC", [("Durham", "NC", "US")]),
    ("Vancouver, WA", [("Vancouver", "WA", "US")]),
    ("Vancouver, BC, Canada", [("Vancouver", "BC", "CA")]),
    ("Kitchener, ON, CA", [("Kitchener", "ON", "CA")]),
    ("Ardmore, PA", [("Ardmore", "PA", "US")]),
    ("Rome, NY", [("Rome", "NY", "US")]),
    ("Washington, D.C.", [("Washington", "DC", "US")]),
    ("Washington, DC", [("Washington", "DC", "US")]),
    ("Mexico", [(None, None, "MX")]),
    ("Jalisco, Mexico", [("Jalisco", None, "MX")]),  # a state; no Mexican admin1 table yet
    ("Montreal (St. Laurent)", [("Montreal", None, None)]),  # the aside is a borough; a gazetteer adds QC
    ("Woodlands, SGP", [("Woodlands", None, "SG")]),
    ("Gloucester,MA", [("Gloucester", "MA", "US")]),
    ("Halifax Regional Municipality, NS, Canada", [("Halifax Regional Municipality", "NS", "CA")]),
    ("Amsterdam, NL", [("Amsterdam", None, "NL")]),
    ("Zaandam, NL, Netherlands", [("Zaandam", None, "NL")]),
    ("Québec City, QC, Canada", [("Quebec City", "QC", "CA")]),  # English name
    ("Tunbridge Wells, UK", [("Tunbridge Wells", None, "GB")]),
    ("Smallville, NL, Netherlands", [("Smallville", None, "NL")]),
    ("Smallville, NL, Canada", [("Smallville", "NL", "CA")]),
    ("St Paul, MN", [("St Paul", "MN", "US")]),  # a gazetteer spells it Saint Paul
    ("Ft Lauderdale, FL", [("Ft Lauderdale", "FL", "US")]),  # a gazetteer spells it Fort Lauderdale
    ("Albany, New York", [("Albany", "NY", "US")]),
    ("Greater Toronto Area", [(None, "ON", "CA")]),  # region GTA
    ("Dallas-Fort Worth Metropolitan Area", [(None, "TX", "US")]),  # region DFW
    ("South SF", [("South San Francisco", "CA", "US")]),
    ("RTP, North Carolina, US", [(None, "NC", "US")]),  # region Research Triangle
    ("Silicon Valley, CA", [(None, "CA", "US")]),  # region Bay Area
    ("Bangalore, Karnataka, India", [("Bengaluru", "KA", "IN")]),
    ("North York, ON, Canada", [("Toronto", "ON", "CA")]),  # a city alias
    ("US-CA-Menlo Park; US-WA-Bellevue", [("Menlo Park", "CA", "US"), ("Bellevue", "WA", "US")]),
    ("US-California-Palo Alto", [("Palo Alto", "CA", "US")]),
    ("United Kingdom-London", [("London", "ENG", "GB")]),
    ("CA-ON-Toronto", [("Toronto", "ON", "CA")]),
    ("Wilkes-Barre, PA", [("Wilkes-Barre", "PA", "US")]),
    ("Japan-Tokyo-Business Tower", [("Tokyo", None, "JP")]),
    ("Seattle, WA + 6 others", [("Seattle", "WA", "US")]),
    ("San Francisco, CA +2 more", [("San Francisco", "CA", "US")]),
    ("Toronto, ON, Canada and 3 more locations", [("Toronto", "ON", "CA")]),
    ("New York, NY; London, UK + 1 other", [("New York City", "NY", "US"), ("London", "ENG", "GB")]),
    ("Geneva, Switzerland", [("Geneva", None, "CH")]),
    ("Cambridge, MA +1", [("Cambridge", "MA", "US")]),
    ("Stafford, VA +2", [("Stafford", "VA", "US")]),
    ("Richmond, CA", [("Richmond", "CA", "US")]),
    ("Richmond, Canada", [("Richmond", "BC", "CA")]),  # admin1 from Metro Vancouver
    (
        "San Leandro, CA; Fremont, CA; Los Lunas, NM",
        [("San Leandro", "CA", "US"), ("Fremont", "CA", "US"), ("Los Lunas", "NM", "US")],
    ),
    ("Portland, OR; Portland, ME", [("Portland", "OR", "US"), ("Portland", "ME", "US")]),
    ("NYC; New York, NY", [("New York City", "NY", "US")]),
    (
        "Texas; Austin, TX; United States",
        [(None, "TX", "US"), ("Austin", "TX", "US"), (None, None, "US")],
    ),
    (
        "Montréal, QC; Zürich, Switzerland; São Paulo, Brazil",
        [("Montréal", "QC", "CA"), ("Zurich", None, "CH"), ("São Paulo", None, "BR")],  # English name
    ),
    ("Central, Hong Kong SAR", [("Central", None, "HK")]),
    ("Aguadilla, PR", [("Aguadilla", "PR", "US")]),
    ("Puerto Rico", [(None, "PR", "US")]),
    (
        "Aguadilla, Puerto Rico, PR; San Juan, Puerto Rico, PR",
        [("Aguadilla", "PR", "US"), ("San Juan", "PR", "US")],
    ),
    ("Fab 7, SG", [(None, None, "SG")]),
    ("Multiple Locations", []),
    ("Multiple Locations, GB", [(None, None, "GB")]),
    ("Headquarters, CA", [(None, "CA", "US")]),
    ("Palo Alto - 1200", [("Palo Alto", None, None)]),  # a gazetteer adds CA, US
    ("San Francisco - SF9", [("San Francisco", None, None)]),
    ("California - San Francisco", [("San Francisco", "CA", "US")]),
    ("Virginia - Mclean", [("Mclean", "VA", "US")]),
    ("MA - Needham", [("Needham", "MA", "US")]),
    ("Ireland Locations, IE", [(None, None, "IE")]),
    ("Launch Complex 2", []),
    ("Dubai - United Arab Emirates", [("Dubai", None, "AE")]),
    ("Northeast - United States", [(None, None, "US")]),
    ("Stoke-on-Trent", [("Stoke-on-Trent", None, None)]),
    ("Plant City, FL", [("Plant City", "FL", "US")]),
    ("North Haven, CT", [("North Haven", "CT", "US")]),
    ("UK & Ireland", [(None, None, "GB"), (None, None, "IE")]),
    (
        "San Francisco HQ; New York City Office",
        [("San Francisco", None, None), ("New York City", "NY", "US")],
    ),
]


@pytest.mark.parametrize(("text", "expected"), LOCATION_CASES)
def test_location_cases(text, expected):
    assert places(text) == expected


# remote listings
REMOTE_CASES = [
    ("Remote", (), []),
    ("Remote - San Francisco, CA", ("US-CA",), [("San Francisco", "CA", "US")]),
    ("Remote in USA", ("US",), [(None, None, "US")]),
    ("Remote - United States", ("US",), [(None, None, "US")]),
    ("USA - Remote", ("US",), [(None, None, "US")]),
    ("Remote in USA; Remote in Canada", ("US", "CA"), [(None, None, "US"), (None, None, "CA")]),
    ("Toronto, ON, Canada; Remote in Canada", ("CA",), [("Toronto", "ON", "CA"), (None, None, "CA")]),
    ("Remote - Austin, TX; Remote in Canada", ("US-TX", "CA"), [("Austin", "TX", "US"), (None, None, "CA")]),
    ("Remote, Zone 1", (), []),
    ("Remote, Hybrid - New York, NY", ("US-NY",), [("New York City", "NY", "US")]),
    ("Remote ; Remote - US and Canada", ("US", "CA"), [(None, None, "US"), (None, None, "CA")]),
]


@pytest.mark.parametrize(("text", "scope", "expected"), REMOTE_CASES)
def test_remote_cases(text, scope, expected):
    parsed = parse_location(text)
    assert parsed.work_mode == "remote"
    assert parsed.remote_scope == scope
    assert places(text) == expected


# bare city names several cities share: settled by `context` and, later, the gazetteer
@pytest.mark.parametrize(
    ("text", "context", "expected"),
    [
        ("London", None, ("London", "ENG", "GB")),
        ("London", "CA", ("London", "ON", "CA")),
        ("Birmingham", None, ("Birmingham", "ENG", "GB")),
        ("Birmingham", "US", ("Birmingham", "AL", "US")),
        ("Dublin", None, ("Dublin", None, "IE")),
        ("Geneva", None, ("Geneva", None, None)),  # needs the gazetteer
    ],
)
def test_bias_cases(text, context, expected):
    assert places(text, context=context)[0] == expected


# work-mode hints in a location string
@pytest.mark.parametrize(
    ("text", "mode"),
    [("Remote, US", "remote"), ("Hybrid - New York, NY", "hybrid"), ("Seattle, WA", None)],
)
def test_work_location_hints(text, mode):
    assert parse_location(text).work_mode == mode


# list formats with unusual separators and orders
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Atlanta GA", [("Atlanta", "GA", "US")]),
        ("Chicago IL USA", [("Chicago", "IL", "US")]),
        ("Cambridge, MA USA", [("Cambridge", "MA", "US")]),
        ("US.AZ.Tempe", [("Tempe", "AZ", "US")]),
        ("US-VA Arlington", [("Arlington", "VA", "US")]),
        ("WI Madison", [("Madison", "WI", "US")]),
        ("TX-SUGAR LAND", [("Sugar Land", "TX", "US")]),
        ("Somerville-MA", [("Somerville", "MA", "US")]),
        ("US | Massachusetts | Boston", [("Boston", "MA", "US")]),
        ("Salem-Virginia-United States of America", [("Salem", "VA", "US")]),
        ("HQ (San Francisco, CA)", [("San Francisco", "CA", "US")]),
        ("Remote (United States)", [(None, None, "US")]),
        ("Rosemont IL", [("Rosemont", "IL", "US")]),
        ("CA-ON-Ottawa, CA-ON-Toronto", [("Ottawa", "ON", "CA"), ("Toronto", "ON", "CA")]),
        ("2 Locations, Ottawa Canada", [("Ottawa", "ON", "CA")]),
        ("Mountain View, CA +29", [("Mountain View", "CA", "US")]),
        ("Toronto, ON, CA", [("Toronto", "ON", "CA")]),
        ("Dubai", [("Dubai", None, None)]),
    ],
)
def test_cleanup_formats(text, expected):
    assert places(text) == expected


# feed formats: "City - Country - ...", "Region - City", "CC-ST-City", "Remote, City, ST, CC"
@pytest.mark.parametrize(
    ("text", "mode", "expected"),
    [
        ("Remote - UK - Remote", "remote", [(None, None, "GB")]),
        ("Mountain View - United States or Remote", "remote", [("Mountain View", "CA", "US")]),
        ("Seoul - South Korea", None, [("Seoul", None, "KR")]),
        ("Canada - Canada", None, [(None, None, "CA")]),
        ("USA - CA - San Francisco", None, [("San Francisco", "CA", "US")]),
        ("Texas - Remote", "remote", [(None, "TX", "US")]),
        ("CA-Remote", "remote", [(None, None, "CA")]),
        ("US-TX-Austin | CA-ON-Ottawa", None, [("Austin", "TX", "US"), ("Ottawa", "ON", "CA")]),
        ("IE-Dublin", None, [("Dublin", None, "IE")]),
        ("Remote, Austin, TX, US", "remote", [("Austin", "TX", "US")]),
    ],
)
def test_feed_formats(text, mode, expected):
    parsed = parse_location(text)
    assert parsed.work_mode == mode
    assert places(text) == expected
