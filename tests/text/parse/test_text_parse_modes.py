"""Work-mode phrases in location strings and the remote scope they set."""

import pytest

from placewise.text import parse_location


def places(parsed):
    """(city, admin1, country) of each primary part."""
    return [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts]


# --- Work modes ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "mode", "scope", "expected"),
    [
        ("Remote", "remote", (), []),
        ("Fully Remote", "remote", (), []),
        ("100% Remote", "remote", (), []),
        ("WFH", "remote", (), []),
        ("Work from home", "remote", (), []),
        ("Anywhere", "remote", (), []),
        ("Remote - Worldwide", "remote", (), []),
        ("Remote - US", "remote", ("US",), [(None, None, "US")]),
        ("US Remote", "remote", ("US",), [(None, None, "US")]),
        ("Remote US", "remote", ("US",), [(None, None, "US")]),
        ("Remote-USA", "remote", ("US",), [(None, None, "US")]),
        ("Remote, Canada", "remote", ("CA",), [(None, None, "CA")]),
        ("Remote (Canada)", "remote", ("CA",), [(None, None, "CA")]),
        ("Canada (Remote)", "remote", ("CA",), [(None, None, "CA")]),
        ("Remote in Canada", "remote", ("CA",), [(None, None, "CA")]),
        ("Remote within the US", "remote", ("US",), [(None, None, "US")]),
        ("Remote (US only)", "remote", ("US",), [(None, None, "US")]),
        ("Anywhere in the United States", "remote", ("US",), [(None, None, "US")]),
        ("Remote - US and Canada", "remote", ("US", "CA"), [(None, None, "US"), (None, None, "CA")]),
        ("Remote US/Canada", "remote", ("US", "CA"), [(None, None, "US"), (None, None, "CA")]),
        ("Remote - Texas", "remote", ("US-TX",), [(None, "TX", "US")]),
        ("Remote - EMEA", "remote", ("EMEA",), []),
        ("Remote, North America", "remote", ("North America",), []),
        ("CA-Remote", "remote", ("CA",), [(None, None, "CA")]),
        ("Hybrid - Toronto, ON", "hybrid", (), [("Toronto", "ON", "CA")]),
        ("Toronto, ON (Hybrid)", "hybrid", (), [("Toronto", "ON", "CA")]),
        ("Hybrid Remote - Seattle, WA", "hybrid", (), [("Seattle", "WA", "US")]),
        ("On-site", "onsite", (), []),
        ("Onsite - Austin, TX", "onsite", (), [("Austin", "TX", "US")]),
        ("On site", "onsite", (), []),
        ("In-person, Boston, MA", "onsite", (), [("Boston", "MA", "US")]),
        ("In office", "onsite", (), []),
        ("Non-remote", "onsite", (), []),
        ("In office 3 days/week", "hybrid", (), []),
        ("New York, NY (in office 3 days a week)", "hybrid", (), [("New York City", "NY", "US")]),
        ("3 days in office - Toronto", "hybrid", (), [("Toronto", None, None)]),
        ("2-3 days per week on-site, Austin, TX", "hybrid", (), [("Austin", "TX", "US")]),
        ("5 days in office", "onsite", (), []),
        ("Toronto, ON", None, (), [("Toronto", "ON", "CA")]),
    ],
)
def test_work_modes(text, mode, scope, expected):
    parsed = parse_location(text)
    assert parsed.work_mode == mode
    assert parsed.remote_scope == scope
    assert places(parsed) == expected
    assert parsed.unparsed == ()


def test_remote_with_a_city_scopes_to_its_region():
    parsed = parse_location("Remote - San Francisco, CA")
    assert parsed.work_mode == "remote"
    assert places(parsed) == [("San Francisco", "CA", "US")]
    assert parsed.parts[0].remote
    assert parsed.remote_scope == ("US-CA",)


def test_remote_or_hybrid_keeps_both_modes():
    parsed = parse_location("Remote or Hybrid")
    assert parsed.work_mode == "remote"
    assert parsed.work_modes == ("remote", "hybrid")


def test_an_office_city_alongside_a_remote_option():
    parsed = parse_location("Toronto, ON or Remote (Canada)")
    assert parsed.work_mode == "remote"
    assert parsed.remote_scope == ("CA",)
    assert [p.remote for p in parsed.parts] == [False, True]


def test_unscoped_remote_beside_a_scoped_one():
    parsed = parse_location("Remote ; Remote - US and Canada")
    assert parsed.remote_scope == ("US", "CA")


def test_prose_is_not_a_place():
    # "in" and "on" inside prose are words, not Indiana or Ontario
    parsed = parse_location("Remote in office on Fridays")
    assert all(p.admin1_code not in {"IN", "ON"} for p in parsed.parts)
