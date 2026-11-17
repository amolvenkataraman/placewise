"""Filter helpers: decisions with the reason a location was kept or dropped."""

import pytest

from placewise.text import (
    Decision,
    LocationFilter,
    in_country,
    in_region,
    is_remote_ok_for,
    parse_location,
)


def test_decision_is_truthy_and_carries_a_reason():
    decision = in_country(parse_location("Toronto, ON"), "CA")
    assert isinstance(decision, Decision)
    assert decision and decision.keep
    assert "Toronto" in decision.reason and "CA" in decision.reason
    assert Decision.from_dict(decision.to_dict()) == decision


# --- in_country ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "country", "keep"),
    [
        ("Toronto, ON", "CA", True),
        ("Toronto, ON", "Canada", True),
        ("Toronto, ON", "CAN", True),
        ("Austin, TX", "CA", False),
        ("Austin, TX; Toronto, ON", "CA", True),
        ("Remote - Canada", "CA", True),
        ("Remote - Texas", "US", True),
        ("GTA", "CA", True),
        ("Bangalore", "IN", True),
        ("Toronto", "CA", False),  # no country without a gazetteer
    ],
)
def test_in_country(text, country, keep):
    assert in_country(parse_location(text), country).keep is keep


def test_in_country_reasons():
    assert in_country(parse_location("Austin, TX"), "CA").reason == "not in CA: Austin, TX (US)"
    assert in_country(parse_location("Toronto"), "CA").reason == "no country found"
    assert in_country(parse_location("Toronto, ON"), ("US", "CA")).reason == "in CA: Toronto, ON"


def test_in_country_alternatives_are_opt_in():
    parsed = parse_location("London")
    assert not in_country(parsed, "CA")
    decision = in_country(parsed, "CA", include_alternatives=True)
    assert decision and "possibly" in decision.reason


# --- in_region ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kwargs", "keep"),
    [
        ("Toronto, ON", {"admin1": ("ON",)}, True),
        ("Toronto, ON", {"admin1": ("CA-ON",)}, True),
        ("Vancouver, BC", {"admin1": ("ON",)}, False),
        ("Toronto, ON", {"metro": ("GTA",)}, True),
        ("Mississauga, Ontario", {"metro": ("GTA",)}, True),
        ("Mississauga, Ontario", {"metro": ("Greater Toronto Area",)}, True),
        ("Ottawa, ON", {"metro": ("GTA",)}, False),
        ("Ottawa, ON", {"admin1": ("ON",), "metro": ("GTA",)}, True),
        ("GTA", {"admin1": ("ON",)}, True),
        ("Mountain View, CA", {"metro": ("Bay Area",)}, True),
        ("Mountain View, CA", {"metro": ("SFBA",)}, True),
        ("Arlington, VA", {"metro": ("DMV",)}, True),
        ("Arlington, TX", {"metro": ("DMV",)}, False),
        ("Arlington, TX", {"metro": ("DFW",)}, True),
        ("DMV", {"admin1": ("VA",)}, True),
        ("Gurgaon", {"metro": ("NCR",)}, True),
        ("Noida, UP, India", {"metro": ("Delhi NCR",)}, True),
    ],
)
def test_in_region(text, kwargs, keep):
    assert in_region(parse_location(text), **kwargs).keep is keep


def test_in_region_city_name_only_is_flagged():
    decision = in_region(parse_location("Mississauga"), metro=("GTA",))
    assert decision and "city name only" in decision.reason


def test_in_region_rejects_unknown_metro():
    with pytest.raises(ValueError, match="unknown metro"):
        in_region(parse_location("Toronto"), metro=("Atlantis",))


# --- is_remote_ok_for ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "country", "keep", "reason"),
    [
        ("Remote", "CA", True, "remote with no location limit"),
        ("Remote - Canada", "CA", True, "remote within CA"),
        ("Remote - US", "CA", False, "remote limited to US"),
        ("Remote - US and Canada", "CA", True, "remote within CA"),
        ("Remote - Texas", "US", True, "remote limited to US-TX"),
        ("Remote - North America", "CA", True, "remote within North America"),
        ("Remote - EMEA", "CA", False, "remote limited to EMEA"),
        ("Remote - EMEA", "GB", True, "remote within EMEA"),
        ("Hybrid - Toronto, ON", "CA", False, "not remote (hybrid)"),
        ("Toronto, ON", "CA", False, "not remote"),
    ],
)
def test_is_remote_ok_for(text, country, keep, reason):
    decision = is_remote_ok_for(parse_location(text), country)
    assert (decision.keep, decision.reason) == (keep, reason)


# --- LocationFilter -----------------------------------------------------------------------------

CANADA_AND_US = LocationFilter(countries=("US", "CA"))


@pytest.mark.parametrize(
    ("text", "keep", "reason"),
    [
        ("Toronto, ON", True, "Toronto, ON is in an allowed country (CA)"),
        ("London, UK", False, "not in an allowed location: London, ENG (GB)"),
        ("London, UK; New York, NY", True, "New York City, NY is in an allowed country (US)"),
        ("Remote", True, "remote with no location limit"),
        ("Remote - UK", False, "remote limited to GB"),
        ("Remote - US", True, "remote within US"),
        ("Multiple Locations", True, "no country found (kept: unknown locations are kept)"),
    ],
)
def test_filter_by_country(text, keep, reason):
    decision = CANADA_AND_US.decide(text)
    assert (decision.keep, decision.reason) == (keep, reason)


def test_filter_from_config():
    config = {
        "countries": ["CA", "US"],
        "admin1": ["CA-ON", "CA-BC"],
        "metros": ["Bay Area", "NYC"],
        "remote": "scoped",
        "unknown": "drop",
    }
    flt = LocationFilter.from_dict(config)
    assert flt.countries == ("CA", "US")
    assert flt.decide("Toronto, ON").keep
    assert flt.decide("Vancouver, BC").keep
    assert not flt.decide("Montreal, QC").keep  # Canada is narrowed to ON and BC
    assert flt.decide("Mountain View, CA").keep
    assert not flt.decide("Austin, TX").keep  # the US is narrowed to the Bay Area and NYC
    assert flt.decide("Remote - US").keep  # remote is judged by country, not narrowed
    decision = flt.decide("Toronto")
    assert (decision.keep, decision.reason) == (
        False,
        "no country found (dropped: unknown locations are dropped)",
    )


def test_filter_reason_names_the_narrowing():
    flt = LocationFilter(countries=("CA",), admin1=("ON",))
    decision = flt.decide("Montreal, QC")
    assert decision.reason == "not in an allowed location: Montreal, QC (CA; allowed there: CA-ON)"


def test_filter_admin1_alone_implies_its_country():
    flt = LocationFilter(admin1=("ON",))
    assert flt.decide("Toronto, ON").keep
    assert not flt.decide("Austin, TX").keep


def test_filter_deny_lists():
    flt = LocationFilter(deny_countries=("IN",), deny_admin1=("US-CA",))
    assert flt.decide("Austin, TX").keep
    decision = flt.decide("Bengaluru, Karnataka")
    assert (decision.keep, decision.reason) == (False, "denied: Bengaluru, KA (IN)")
    assert not flt.decide("San Francisco, CA").keep
    assert flt.decide("San Francisco, CA; Austin, TX").keep


@pytest.mark.parametrize(
    ("policy", "text", "keep"),
    [
        ("any", "Remote - UK", True),
        ("scoped", "Remote", True),
        ("strict", "Remote", False),
        ("strict", "Remote - Canada", True),
        ("deny", "Remote - Canada", False),
        ("deny", "Toronto, ON or Remote (Canada)", True),
    ],
)
def test_filter_remote_policy(policy, text, keep):
    flt = LocationFilter(countries=("CA",), remote=policy)
    assert flt.decide(text).keep is keep


def test_filter_work_modes():
    flt = LocationFilter(countries=("CA",), work_modes=("remote", "hybrid"))
    assert flt.decide("Hybrid - Toronto, ON").keep
    decision = flt.decide("On-site - Toronto, ON")
    assert (decision.keep, decision.reason) == (False, "work mode onsite is not allowed")
    assert flt.decide("Toronto, ON").keep  # an unstated mode isn't held against the location


def test_filter_validates_its_config():
    with pytest.raises(ValueError, match="remote"):
        LocationFilter(remote="sometimes")
    with pytest.raises(ValueError, match="unknown country"):
        LocationFilter(countries=("Atlantis",))
    with pytest.raises(ValueError, match="ambiguous"):
        LocationFilter(admin1=("TN",))  # Tennessee or Tamil Nadu
    assert LocationFilter(countries=("IN",), admin1=("TN",)).admin1 == ("IN-TN",)
    assert LocationFilter(countries=("Canada",)).countries == ("CA",)


def test_filter_alternatives_opt_in():
    assert not LocationFilter(countries=("CA",)).decide("London").keep
    assert LocationFilter(countries=("CA",), include_alternatives=True).decide("London").keep


def test_filter_uses_the_gazetteer():
    class Gazetteer:
        def match(self, city, country_iso2, admin1_code):
            from placewise.model.places import Place

            if city == "Toronto" and country_iso2 in (None, "CA"):
                return Place("test:toronto", "Toronto", "locality", codes={"iso2": "CA", "admin1": "ON"})
            return None

    flt = LocationFilter(countries=("CA",), unknown="drop")
    assert not flt.decide("Toronto").keep
    assert flt.decide("Toronto", gazetteer=Gazetteer()).keep


# --- Structured addresses -----------------------------------------------------------------------
from placewise.text import parse_address  # noqa: E402


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        # JSON-LD PostalAddress
        (
            {"addressLocality": "Menlo Park", "addressRegion": "CA", "addressCountry": "US"},
            ("Menlo Park", "CA", "US"),
        ),
        (
            {"addressLocality": "Toronto", "addressRegion": "ON", "addressCountry": {"name": "Canada"}},
            ("Toronto", "ON", "CA"),
        ),
        # city / stateCode / countryCode
        ({"city": "Austin", "stateCode": "TX", "countryCode": "US"}, ("Austin", "TX", "US")),
        # city / state / country names
        ({"city": "Toronto", "state": "Ontario", "country": "Canada"}, ("Toronto", "ON", "CA")),
        ({"addressRegion": "Texas"}, (None, "TX", "US")),
    ],
)
def test_parse_address(address, expected):
    (part,) = parse_address(address).parts
    assert (part.city, part.admin1_code, part.country_iso2) == expected


def test_parse_address_remote_flag():
    parsed = parse_address({"countryCode": "US"}, remote=True)
    assert parsed.work_mode == "remote" and parsed.remote_scope == ("US",)
