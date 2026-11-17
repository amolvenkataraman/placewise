"""Which place a part means: metros, city aliases, ambiguity rules, context and evidence."""

import pytest

from placewise.text import parse_location


def places(parsed):
    """(city, admin1, country) of each primary part."""
    return [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts]


# --- Metros -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "region", "expected"),
    [
        ("GTA", "GTA", (None, "ON", "CA")),
        ("Greater Toronto Area", "GTA", (None, "ON", "CA")),
        ("GTHA", "GTA", (None, "ON", "CA")),
        ("SF Bay Area", "Bay Area", (None, "CA", "US")),
        ("Bay Area", "Bay Area", (None, "CA", "US")),
        ("SFBA", "Bay Area", (None, "CA", "US")),
        ("Silicon Valley, CA", "Bay Area", (None, "CA", "US")),
        ("SF", "Bay Area", ("San Francisco", "CA", "US")),
        ("NYC", "NYC", ("New York City", "NY", "US")),
        ("New York Metro", "NYC", (None, None, "US")),
        ("LA", "Greater Los Angeles", ("Los Angeles", "CA", "US")),
        ("Greater Vancouver", "Metro Vancouver", (None, "BC", "CA")),
        ("Delhi NCR", "NCR", (None, None, "IN")),
        ("Bangalore, Karnataka, India", "Bengaluru", ("Bengaluru", "KA", "IN")),
        ("Bengaluru", "Bengaluru", ("Bengaluru", "KA", "IN")),
        ("Gurgaon", "NCR", ("Gurugram", "HR", "IN")),
        ("Greater Seattle Area", "Greater Seattle", (None, "WA", "US")),
        ("DFW", "DFW", (None, "TX", "US")),
        ("Dallas-Fort Worth Metropolitan Area", "DFW", (None, "TX", "US")),
        ("DMV", "DMV", (None, None, "US")),
        ("RTP, North Carolina, US", "Research Triangle", (None, "NC", "US")),
        ("Toronto, ON", "GTA", ("Toronto", "ON", "CA")),
        ("Mountain View, CA", "Bay Area", ("Mountain View", "CA", "US")),
    ],
)
def test_metros(text, region, expected):
    parsed = parse_location(text)
    assert places(parsed) == [expected]
    assert parsed.parts[0].region == region


def test_baton_rouge_la_is_louisiana_not_los_angeles():
    assert places(parse_location("Baton Rouge, LA")) == [("Baton Rouge", "LA", "US")]


# --- Ambiguity ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("London, ON", ("London", "ON", "CA")),
        ("Bloomington, IN", ("Bloomington", "IN", "US")),
        ("London, ON, Canada", ("London", "ON", "CA")),
    ],
)
def test_on_and_in_after_a_comma_are_codes(text, expected):
    assert places(parse_location(text)) == [expected]


@pytest.mark.parametrize("text", ["Work on site", "Based in office", "Remote in or near Austin"])
def test_on_and_in_inside_prose_are_words(text):
    codes = {p.admin1_code for p in parse_location(text).parts}
    assert not codes & {"ON", "IN"}


def test_london_alone_is_ambiguous():
    (part,) = parse_location("London").parts
    assert (part.city, part.country_iso2) == ("London", "GB")
    assert part.alternatives
    alt = part.alternatives[0]
    assert (alt.city, alt.admin1_code, alt.country_iso2) == ("London", "ON", "CA")
    assert part.confidence > alt.confidence > 0
    assert part.confidence + sum(a.confidence for a in part.alternatives) == pytest.approx(1.0)


def test_london_in_a_canadian_context_prefers_ontario():
    (part,) = parse_location("London", context="CA").parts
    assert (part.admin1_code, part.country_iso2) == ("ON", "CA")
    assert part.alternatives[0].country_iso2 == "GB"
    # other places in the same string set the context too
    parsed = parse_location("Toronto, ON; London")
    assert parsed.parts[1].country_iso2 == "CA"


def test_london_with_its_country_is_not_ambiguous():
    (part,) = parse_location("London, UK").parts
    assert (part.city, part.country_iso2, part.alternatives) == ("London", "GB", ())


def test_georgia_alone_is_ambiguous():
    (part,) = parse_location("Georgia").parts
    candidates = {(part.admin1_code, part.country_iso2)} | {
        (a.admin1_code, a.country_iso2) for a in part.alternatives
    }
    assert candidates == {("GA", "US"), (None, "GE")}
    assert part.confidence == pytest.approx(0.5)


def test_georgia_in_a_us_context_is_the_state():
    (part,) = parse_location("Georgia", context="US").parts
    assert (part.admin1_code, part.country_iso2) == ("GA", "US")
    parsed = parse_location("Austin, TX; Georgia")
    assert parsed.parts[1].iso_3166_2 == "US-GA"
    assert parsed.parts[1].confidence >= 0.9


def test_georgia_with_a_us_city_is_the_state():
    (part,) = parse_location("Atlanta, Georgia").parts
    assert part.iso_3166_2 == "US-GA" and part.confidence >= 0.9
    (part,) = parse_location("Tbilisi, Georgia").parts
    assert (part.admin1_code, part.country_iso2) == (None, "GE")
    (part,) = parse_location("Georgia, USA").parts
    assert part.iso_3166_2 == "US-GA" and part.confidence == 1.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ontario", (None, "ON", "CA")),
        ("Ontario, Canada", (None, "ON", "CA")),
        ("Ontario, CA", ("Ontario", "CA", "US")),
        ("Ontario, OH", ("Ontario", "OH", "US")),
        ("Washington, PA", ("Washington", "PA", "US")),
        ("Washington", (None, "WA", "US")),
        ("Albany, New York", ("Albany", "NY", "US")),
        ("Texas", (None, "TX", "US")),
        ("Kitchener, ON, CA", ("Kitchener", "ON", "CA")),
        ("Smallville, NL, Netherlands", ("Smallville", None, "NL")),
        ("Smallville, NL, Canada", ("Smallville", "NL", "CA")),
        ("Amsterdam, NL", ("Amsterdam", None, "NL")),
        ("Aguadilla, PR", ("Aguadilla", "PR", "US")),
        ("Puerto Rico", (None, "PR", "US")),
        ("Chennai, TN, India", ("Chennai", "TN", "IN")),
        ("Hyderabad, TS, India", ("Hyderabad", "TS", "IN")),
        ("Mumbai, MH", ("Mumbai", "MH", "IN")),
        ("Pune, Maharashtra", ("Pune", "MH", "IN")),
        ("Delhi, India", ("Delhi", "DL", "IN")),
        ("New York", ("New York City", "NY", "US")),
    ],
)
def test_region_and_city_name_clashes(text, expected):
    assert places(parse_location(text)) == [expected]


def test_city_ca_is_california_with_canada_as_the_alternative():
    (part,) = parse_location("Smallville, CA").parts
    assert part.iso_3166_2 == "US-CA"
    assert part.alternatives[0].country_iso2 == "CA"
    (part,) = parse_location("Smallville, CA", context="CA").parts
    assert part.country_iso2 == "CA"


# --- Found by an ad-hoc sweep after the first green run -----------------------------------------


@pytest.mark.parametrize(("text", "scope"), [("Remote, IN", ("IN",)), ("Remote in IN", ("IN",))])
def test_a_code_after_remote_survives_the_preposition_stripper(text, scope):
    assert parse_location(text).remote_scope == scope


def test_a_bare_in_is_indiana_with_india_as_the_alternative():
    (part,) = parse_location("IN").parts
    assert part.iso_3166_2 == "US-IN"
    assert part.alternatives[0].country_iso2 == "IN"


@pytest.mark.parametrize("text", ["Kansas City, MO", "Pittsburgh, PA", "Savannah, GA", "Boise, ID"])
def test_state_codes_that_are_obscure_country_codes_read_only_as_states(text):
    (part,) = parse_location(text).parts
    assert part.country_iso2 == "US" and part.alternatives == () and part.confidence == 1.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Toronto, GTA", ("Toronto", "ON", "CA", "GTA")),
        ("Ontario, GTA", (None, "ON", "CA", "GTA")),
        ("SF, Bay Area", ("San Francisco", "CA", "US", "Bay Area")),
        ("Washington, D.C. Metro Area", ("Washington", "DC", "US", "DMV")),
    ],
)
def test_a_metro_after_its_city_is_one_place(text, expected):
    (part,) = parse_location(text).parts
    assert (part.city, part.admin1_code, part.country_iso2, part.region) == expected


@pytest.mark.parametrize("text", ["N/A", "TBD", "TBA", "Not specified"])
def test_placeholders_are_not_cities(text):
    parsed = parse_location(text)
    assert parsed.parts == () and parsed.unparsed == (text,)


def test_office_days_in_parentheses_are_part_of_the_mode():
    parsed = parse_location("Hybrid (3 days/week) - San Francisco, CA")
    assert parsed.work_mode == "hybrid" and parsed.unparsed == ()


# --- City aliases, GB nations, alpha-3 in any case, postal codes ----------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PDX", ("Portland", "OR", "US")),
        ("YYZ", ("Toronto", "ON", "CA")),
        ("TOR", ("Toronto", "ON", "CA")),
        ("Philly", ("Philadelphia", "PA", "US")),
        ("STL", ("St. Louis", "MO", "US")),
        ("NOLA", ("New Orleans", "LA", "US")),
        ("YYC", ("Calgary", "AB", "CA")),
        ("MTL", ("Montreal", "QC", "CA")),
        ("KW", ("Kitchener", "ON", "CA")),
        ("DC", ("Washington", "DC", "US")),
        ("NY", ("New York City", "NY", "US")),
        ("HK", ("Hong Kong", None, "HK")),
        ("Saigon", ("Ho Chi Minh City", None, "VN")),
        ("North York, ON, Canada", ("Toronto", "ON", "CA")),
        ("Quebec City", ("Quebec City", "QC", "CA")),
    ],
)
def test_real_world_city_aliases(text, expected):
    (part,) = parse_location(text).parts
    assert (part.city, part.admin1_code, part.country_iso2) == expected


def test_a_short_alias_is_a_city_only_alone():
    # a lone short code is a city alias; beside other parts it's a code
    (part,) = parse_location("NY, USA").parts
    assert (part.city, part.admin1_code, part.country_iso2) == (None, "NY", "US")
    (part,) = parse_location("Albany, NY").parts
    assert part.city == "Albany"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("London, England", ("London", "ENG", "GB")),
        ("Edinburgh, Scotland", ("Edinburgh", "SCT", "GB")),
        ("Cardiff, Wales, UK", ("Cardiff", "WLS", "GB")),
        ("Belfast, Northern Ireland", ("Belfast", "NIR", "GB")),
    ],
)
def test_uk_nations_are_admin1(text, expected):
    (part,) = parse_location(text).parts
    assert (part.city, part.admin1_code, part.country_iso2) == expected
    assert not part.alternatives


@pytest.mark.parametrize(
    ("text", "country"), [("Toronto, Can", "CA"), ("Pune, Ind", "IN"), ("Sydney, Aus", "AU")]
)
def test_common_alpha3_codes_read_in_any_case(text, country):
    assert parse_location(text).parts[0].country_iso2 == country


def test_other_alpha3_codes_need_capitals():
    assert parse_location("Lima, PER").parts[0].country_iso2 == "PE"
    assert parse_location("Lima, per").parts[0].country_iso2 is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Springfield, IL 62701", ("Springfield", "IL", "US")),
        ("Tempe, AZ 85281-1234", ("Tempe", "AZ", "US")),
        ("Toronto, ON M5V 2T6", ("Toronto", "ON", "CA")),
        ("Bengaluru, Karnataka 560001, India", ("Bengaluru", "KA", "IN")),
    ],
)
def test_postal_codes_are_dropped(text, expected):
    parsed = parse_location(text)
    assert [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts] == [expected]
    assert parsed.unparsed == ()
