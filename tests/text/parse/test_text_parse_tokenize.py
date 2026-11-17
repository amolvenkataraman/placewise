"""One place-string into parts: abbreviations, case, spacing, noise, leftovers, postal codes."""

import pytest

from placewise.text import parse_location


def places(parsed):
    """(city, admin1, country) of each primary part."""
    return [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts]


# --- Abbreviations, case and whitespace ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("New York, N.Y.", ("New York City", "NY", "US")),
        ("Albany, N.Y.", ("Albany", "NY", "US")),
        ("Ottawa, Ont.", ("Ottawa", "ON", "CA")),
        ("Ottawa, Ont", ("Ottawa", "ON", "CA")),
        ("Montreal, Que.", ("Montreal", "QC", "CA")),
        ("Montréal, Québec", ("Montréal", "QC", "CA")),
        ("Sacramento, Calif.", ("Sacramento", "CA", "US")),
        ("Washington, D.C.", ("Washington", "DC", "US")),
        ("Washington DC", ("Washington", "DC", "US")),
        ("Charleston, W. Va.", ("Charleston", "WV", "US")),
        ("Austin, Texas, U.S.", ("Austin", "TX", "US")),
        ("Austin, Texas, U.S.A.", ("Austin", "TX", "US")),
        ("Halifax, N.S.", ("Halifax", "NS", "CA")),
        ("Charlottetown, P.E.I.", ("Charlottetown", "PE", "CA")),
    ],
)
def test_abbreviations_with_and_without_dots(text, expected):
    assert places(parse_location(text)) == [expected]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("SAN FRANCISCO, CA", ("San Francisco", "CA", "US")),
        ("TORONTO, ON, CANADA", ("Toronto", "ON", "CA")),
        ("CEDAR RAPIDS IA", ("Cedar Rapids", "IA", "US")),
        ("toronto, on", ("toronto", "ON", "CA")),
        ("  Toronto ,   ON  ", ("Toronto", "ON", "CA")),
        ("New   York,\tNY", ("New York City", "NY", "US")),
    ],
)
def test_case_and_whitespace(text, expected):
    assert places(parse_location(text)) == [expected]


@pytest.mark.parametrize("dash", ["–", "—", "‐", "‑", "−"])
def test_unicode_dashes(dash):
    parsed = parse_location(f"Remote {dash} Canada")
    assert parsed.work_mode == "remote"
    assert parsed.remote_scope == ("CA",)
    parsed = parse_location(f"California {dash} San Francisco")
    assert places(parsed) == [("San Francisco", "CA", "US")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Toronto Office", ("Toronto", None, None)),
        ("San Francisco HQ, CA", ("San Francisco", "CA", "US")),
        ("Headquarters - Austin, TX", ("Austin", "TX", "US")),
        ("Downtown Toronto, ON", ("Toronto", "ON", "CA")),
        ("Toronto Downtown, ON", ("Toronto", "ON", "CA")),
        ("Greater Boston Area", (None, None, "US")),  # the metro reaches into NH
        ("Metro Vancouver", (None, "BC", "CA")),
        ("Mountain View Campus, CA", ("Mountain View", "CA", "US")),
    ],
)
def test_noise_words(text, expected):
    assert places(parse_location(text)) == [expected]


# --- Leftovers ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected", "unparsed"),
    [
        ("Montreal (St. Laurent)", [("Montreal", None, None)], ("St. Laurent",)),
        ("Remote, Zone 1", [], ("Zone 1",)),
        ("Palo Alto - 1200", [("Palo Alto", None, None)], ("1200",)),
        ("Japan-Tokyo-Business Tower", [("Tokyo", None, "JP")], ("Business Tower",)),
    ],
)
def test_unparsed_leftovers(text, expected, unparsed):
    parsed = parse_location(text)
    assert places(parsed) == expected
    assert parsed.unparsed == unparsed
