"""The readable text card of a Result or Entity (`str(x)`, `x.card()`): placewise.model.display."""

import dataclasses
import io
import re

import pytest
from display_kit import disputed_answer, lake_answer, paris_texas, yosemite_valley

import placewise.model as model
from placewise.model import Entity, Place, PlaceKind, Result
from placewise.model.display import text

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def rows(card):
    """{field: (value, source)} from a plain card's aligned lines."""
    out = {}
    for line in card.splitlines()[1:]:
        m = re.match(r"^  (\S+) +(.*?)(?: {2,}(\S+))?$", line)
        assert m, line
        out[m[1]] = (m[2], m[3])
    return out


def test_first_line_is_the_label_and_the_coordinates():
    card = str(yosemite_valley())
    assert card.splitlines()[0] == "Yosemite Valley, Yosemite National Park  (37.72840, -119.61150)"


def test_one_aligned_line_per_filled_field_in_order_with_its_source():
    card = str(yosemite_valley())
    got = rows(card)
    assert list(got) == ["locality", "city", "admin2", "admin1", "country", "postal", "within", "near", "tz"]
    assert got["locality"] == ("Yosemite Valley", "usa/places:polygon")
    assert got["admin1"] == ("California (US-CA)", "usa/states:polygon")
    assert got["country"] == ("United States (US)", "world/countries:polygon")
    assert got["within"] == (
        "Yosemite National Park · Sierra National Forest",
        "usa-parks/parks_national:polygon",
    )
    # the nearest three, with distance and compass point
    assert got["near"] == ("El Portal 18 km W · Wawona 24 km S · Mariposa 49 km SW", "world/cities:nearest")
    assert got["tz"] == ("America/Los_Angeles", "usa/timezones:polygon")
    # values start in one column, sources end at the right edge
    lines = card.splitlines()[1:]
    assert len({len(re.match(r"^  \S+ +", line)[0]) for line in lines}) == 1
    assert max(map(len, lines)) <= 100
    assert all(len(line) == max(map(len, lines)) for line in lines if line.endswith(("polygon", "nearest")))


def test_empty_fields_leave_no_line():
    card = str(Result(lat=10.0, lon=20.0))
    assert card == "(10.00000, 20.00000)"
    assert "sublocality" not in str(yosemite_valley()) and "borough" not in str(yosemite_valley())


def test_water_airport_and_disputed():
    got = rows(str(lake_answer()))
    assert got["water"] == ("on Lake Tahoe, shore 6.7 km E", "world-water/lakes:polygon")
    assert got["airport"] == ("Lake Tahoe Airport (TVL) 9.0 km SE", "world/airports:nearest")
    d = rows(str(disputed_answer()))["disputed"][0]
    assert d == "An Area: claimed by XA, XB; administered by XA; de_facto view"


def test_width_never_exceeds_100_columns():
    long_name = "A Very Long Park Name " * 8
    parks = tuple(Place(f"p:{i}", f"{long_name}{i}", PlaceKind.PARK, tier=1) for i in range(3))
    r = dataclasses.replace(yosemite_valley(), within=parks, label="x" * 140)
    for line in str(r).splitlines():
        assert len(line) <= 100
    assert "…" in str(r)
    assert all(len(line) <= 60 for line in r.card(width=60).splitlines())


def test_plain_by_default_colour_only_on_a_terminal(monkeypatch):
    r = yosemite_valley()
    assert not ANSI.search(str(r)) and not ANSI.search(r.card())
    coloured = r.card(color=True)
    assert ANSI.search(coloured) and ANSI.sub("", coloured) == str(r)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr("sys.stdout", Tty())
    assert text.use_color(None) and ANSI.search(r.card())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not text.use_color(None) and not ANSI.search(r.card())
    monkeypatch.setattr("sys.stdout", io.StringIO())
    monkeypatch.delenv("NO_COLOR")
    assert not text.use_color(None)


def test_repr_is_unchanged_and_round_trips():
    r = yosemite_valley()
    assert repr(r).startswith("Result(lat=37.7284, lon=-119.6115, label='Yosemite Valley, Yosemite National")
    assert "kind=PlaceKind.COUNTRY" in repr(r)
    namespace = {name: getattr(model, name) for name in model.__all__}
    for x in (r, lake_answer(), disputed_answer(), paris_texas()):
        assert eval(repr(x), namespace) == x  # our own repr


def test_entity_card():
    card = str(paris_texas())
    lines = card.splitlines()
    assert lines[0] == "Paris  (Texas, US)"
    got = rows(card)
    assert got["kind"] == ("locality", None)
    assert got["point"] == ("33.66094, -95.55551", None)
    assert got["extent"][0] == "13.0 × 13.3 km box · radius 8.4 km"
    assert got["id"] == ("geonames:4717560", "geonames")
    assert got["score"] == ("0.912", None)
    assert got["alternates"] == ("2: census:4855000, x:1", None)
    assert got["aliases"] == ("Paris, Texas", None)
    assert max(map(len, lines)) <= 100


def test_entity_card_without_extras_and_with_a_tier():
    e = paris_texas()
    park = Place("nps:YOSE", "Yosemite National Park", PlaceKind.PARK, tier=1)
    bare = Entity(place=park, point=e.point, bbox=e.bbox, radius_km=0.0)
    got = rows(str(bare))
    assert str(bare).splitlines()[0] == "Yosemite National Park"
    assert got["kind"] == ("park, tier 1", None)
    assert "score" not in got and "alternates" not in got and "aliases" not in got
    assert got["extent"][0] == "13.0 × 13.3 km box"


@pytest.mark.parametrize("obj", [yosemite_valley(), paris_texas()])
def test_str_is_the_plain_card(obj):
    assert str(obj) == obj.card(color=False) == text.card(obj)


def test_fields_filled_from_outside_say_how_far():
    from placewise.model import Match, Relation

    r = dataclasses.replace(
        yosemite_valley(),
        matches={"locality": Match(Relation.WITHIN, 0.0), "city": Match(Relation.NEAR, 3.14)},
    )
    got = rows(str(r))
    assert got["locality"][0] == "Yosemite Valley"  # inside: nothing added
    assert got["city"][0] == "Yosemite Valley · 3.1 km away, not inside"
    off = dataclasses.replace(
        r, matches={"country": Match(Relation.OFFSHORE, 4.0), "city": Match(Relation.NEAR)}
    )
    got = rows(str(off))
    assert got["country"][0] == "United States (US) · 4.0 km offshore"
    assert got["city"][0] == "Yosemite Valley · not inside"


def test_entity_card_says_when_its_context_is_unsure():
    from placewise.model import Match, Relation

    e = paris_texas()
    inside = {"country": Match(Relation.WITHIN, 0.0), "region": Match(Relation.WITHIN, 0.0)}
    sure = dataclasses.replace(e, context_matches=inside)
    assert str(sure).splitlines()[0] == "Paris  (Texas, US)"
    border = dataclasses.replace(sure, context_certain=False)
    assert str(border).splitlines()[0] == "Paris  (Texas, US · near a border)"
    off = dataclasses.replace(border, context_matches={**inside, "country": Match(Relation.OFFSHORE, 4.0)})
    assert str(off).splitlines()[0] == "Paris  (Texas, US · offshore)"
    gap = dataclasses.replace(border, context_matches={**inside, "region": Match(Relation.NEAR, 0.2)})
    assert str(gap).splitlines()[0] == "Paris  (Texas, US · outside its outline)"
