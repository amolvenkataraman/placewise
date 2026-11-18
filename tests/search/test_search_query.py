"""Reading a search query: name and context, codes, ids, coordinates, aliases, fallbacks."""

import pytest

from placewise.search.query import parse_query


def test_plain_name():
    q = parse_query("  Toronto ")
    assert q.name == "Toronto" and q.key == "toronto"
    assert q.context == () and q.context_place is None and q.point is None and not q.is_id


def test_name_comma_admin1_code():
    q = parse_query("Springfield, IL")
    assert q.name == "Springfield" and q.key == "springfield"
    assert q.context[0] == ("US", "IL")


def test_name_comma_country():
    assert parse_query("Paris, France").context == (("FR", None),)
    assert parse_query("Paris, TX").context == (("US", "TX"),)


def test_several_context_parts_narrow_each_other():
    # "CA" alone is California first, Canada second; with "Canada" beside it, only the country fits
    q = parse_query("London, ON, Canada")
    assert q.name == "London" and q.context == (("CA", "ON"),)
    assert parse_query("Springfield, IL, USA").context == (("US", "IL"),)


def test_context_that_is_not_a_region_is_a_place():
    q = parse_query("Union Station, Toronto")
    assert q.name == "Union Station" and q.context == () and q.context_place == "Toronto"


def test_street_abbreviations_share_the_city_key():
    assert parse_query("St. Catharines").key == parse_query("Saint Catharines").key


def test_codes_and_ids():
    for code in ("YYZ", "CYYZ", "M5V", "94105", "560001", "CA-ON", "US", "IND", "Q1049470"):
        assert parse_query(code).code_like, code
    for not_code in ("Lake Tahoe", "Toronto Pearson International"):
        assert not parse_query(not_code).code_like
    q = parse_query("census:0646870")
    assert q.is_id and q.id == "census:0646870"
    assert parse_query("wikidata:Q1049470").id == "wikidata:Q1049470"
    assert parse_query("iso:IN-KA").is_id
    assert not parse_query("Paris, TX").is_id


def test_bare_wikidata_qid_is_also_read_as_its_id():
    assert parse_query("Q1049470").id == "wikidata:Q1049470"
    assert parse_query("q42").id == "wikidata:Q42"


@pytest.mark.parametrize(
    ("text", "point"),
    [
        ("43.6426, -79.3871", (43.6426, -79.3871)),
        ("43°38′33.2″N 79°23′13.4″W", (43.642556, -79.387056)),
        ("https://www.google.com/maps/@43.6426,-79.3871,15z", (43.6426, -79.3871)),
    ],
)
def test_coordinates(text, point):
    q = parse_query(text)
    assert q.point == pytest.approx(point, abs=1e-5)


@pytest.mark.parametrize("text", ["94105", "560001", "M5V", "Highway 401", "1600 Amphitheatre"])
def test_numbers_that_are_not_coordinates(text):
    assert parse_query(text).point is None


def test_city_aliases_from_location_search_add_a_key_with_its_context():
    q = parse_query("Bangalore")
    assert ("bengaluru", ("IN", "KA")) in q.aliases
    assert ("gurugram", ("IN", "HR")) in parse_query("Gurgaon").aliases
    assert ("mumbai", ("IN", "MH")) in parse_query("Bombay").aliases
    assert parse_query("Toronto").aliases == ()


def test_metro_names_give_the_region_id():
    assert parse_query("GTA").region_ids == ("region:gta",)
    assert parse_query("Delhi NCR").region_ids == ("region:delhi-ncr",)
    assert parse_query("Bay Area").region_ids == ("region:sf-bay-area",)
    assert parse_query("Lake Tahoe").region_ids == ()


def test_fallback_names_drop_generic_words():
    assert "peel" in parse_query("Peel Region").fallback_keys
    assert "toronto" in parse_query("City of Toronto").fallback_keys
    assert parse_query("Toronto").fallback_keys == ()


def test_trailing_word_context_is_a_fallback_reading():
    q = parse_query("Paris TX")
    assert q.trailing is not None
    assert q.trailing.key == "paris" and q.trailing.context == (("US", "TX"),)
    assert parse_query("Clark County").trailing is None


def test_empty_query_is_an_error():
    with pytest.raises(ValueError, match="empty"):
        parse_query("   ")
