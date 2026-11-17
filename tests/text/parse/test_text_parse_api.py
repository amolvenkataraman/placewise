"""parse_location and parse_address: result shape, offsets, round trips, the gazetteer hook."""

import pytest

from placewise.model.places import Place, PlaceKind
from placewise.text import LocationPart, ParsedLocation, parse_location


def places(parsed):
    """(city, admin1, country) of each primary part."""
    return [(p.city, p.admin1_code, p.country_iso2) for p in parsed.parts]


# --- Shape --------------------------------------------------------------------------------------


def test_result_shape():
    parsed = parse_location("Toronto, ON")
    assert isinstance(parsed, ParsedLocation)
    assert parsed.raw == "Toronto, ON"
    (part,) = parsed.parts
    assert isinstance(part, LocationPart)
    assert part.city == "Toronto"
    assert part.admin1_code == "ON"
    assert part.admin1_name == "Ontario"
    assert part.country_iso2 == "CA"
    assert part.iso_3166_2 == "CA-ON"
    assert part.city_verified is False
    assert part.span == (0, 11)
    assert part.confidence == 1.0
    assert parsed.work_mode is None and not parsed.multiple and parsed.unparsed == ()


def test_round_trips_through_dicts():
    parsed = parse_location("Hybrid - London; Remote (Canada)")
    assert ParsedLocation.from_dict(parsed.to_dict()) == parsed


def test_frozen():
    parsed = parse_location("Toronto")
    with pytest.raises(AttributeError):
        parsed.raw = "x"


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty(text):
    parsed = parse_location(text)
    assert parsed.parts == () and parsed.work_mode is None


def test_span_points_at_the_text():
    raw = "Remote; Austin, TX or  Vancouver, BC"
    parsed = parse_location(raw)
    assert [raw[slice(*p.span)] for p in parsed.parts] == ["Austin, TX", "Vancouver, BC"]


# --- Gazetteer hook -----------------------------------------------------------------------------


class FakeGazetteer:
    """Knows a handful of cities, the way a data pack would."""

    CITIES = frozenset(
        {
            ("toronto", "CA", "ON"),
            ("london", "GB", "ENG"),
            ("london", "CA", "ON"),
            ("tokyo", "JP", None),
            ("taylor", "US", "TX"),
            ("toronto", "US", "OH"),
        }
    )

    def __init__(self):
        self.calls = []

    def match(self, city, country_iso2, admin1_code):
        self.calls.append((city, country_iso2, admin1_code))
        for name, country, admin1 in self.CITIES:
            if name == city.lower() and country_iso2 in (None, country) and admin1_code in (None, admin1):
                return Place(
                    id=f"test:{name}-{country}",
                    name=city.title(),
                    kind=PlaceKind.LOCALITY,
                    codes={"iso2": country, **({"admin1": admin1} if admin1 else {})},
                )
        return None


def test_gazetteer_verifies_a_city():
    gazetteer = FakeGazetteer()
    (part,) = parse_location("Toronto, ON", gazetteer=gazetteer).parts
    assert part.city_verified and part.place.id == "test:toronto-CA"
    assert ("Toronto", "CA", "ON") in gazetteer.calls


def test_gazetteer_places_a_bare_city():
    (part,) = parse_location("Toronto", gazetteer=FakeGazetteer(), context="CA").parts
    assert (part.admin1_code, part.country_iso2, part.city_verified) == ("ON", "CA", True)


def test_gazetteer_picks_the_reading_it_knows():
    # "CA" reads as California first; only the Canadian reading names a known city
    (part,) = parse_location("Toronto, CA", gazetteer=FakeGazetteer()).parts
    assert part.country_iso2 == "CA" and part.city_verified


def test_gazetteer_keeps_only_verified_candidates():
    (part,) = parse_location("London", gazetteer=FakeGazetteer()).parts
    assert part.city_verified and all(a.city_verified for a in part.alternatives)


def test_gazetteer_finds_a_city_inside_site_text():
    parsed = parse_location("Site 4 Taylor, TX", gazetteer=FakeGazetteer())
    assert places(parsed) == [("Taylor", "TX", "US")]


def test_unknown_city_stays_unverified():
    (part,) = parse_location("Smallville, TX", gazetteer=FakeGazetteer()).parts
    assert (part.city, part.city_verified, part.place) == ("Smallville", False, None)
