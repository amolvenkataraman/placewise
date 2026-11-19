"""Parks on the real packs (usa-parks, can-parks, eur-parks, world-parks): public places only.

Skipped when a pack isn't built (`uv run python -m packbuild.parks usa can eur world`).
"""

import pytest
from e2e_kit import geocoder, us_parks

from placewise.model import PlaceKind


def within(packs, lat, lon):
    return [p.name for p in geocoder(*packs).lookup(lat, lon).within]


def near_parks(packs, lat, lon):
    return {
        n.place.name: n.distance_km
        for n in geocoder(*packs).lookup(lat, lon).near
        if n.place.kind == PlaceKind.PARK
    }


@pytest.mark.parametrize(
    ("pack", "point", "park"),
    [
        ("usa-parks", (37.7456, -119.5936), "Yosemite National Park"),  # Yosemite Valley
        ("usa-parks", (40.7829, -73.9654), "Central Park"),  # Central Park, New York
        ("can-parks", (51.4254, -116.1773), "Banff National Park"),  # Lake Louise
        pytest.param(
            "can-parks",
            (43.82, -79.17),
            "Rouge National Urban Park",
            marks=pytest.mark.xfail(reason="the 2026.11 build's Rouge outline misses points inside it: open"),
        ),  # Rouge Park, Toronto
    ],
)
def test_within(pack, point, park):
    found = within(("world", *(us_parks() if pack == "usa-parks" else (pack,))), *point)
    assert found and found[0] == park if pack == "can-parks" else park in found


@pytest.mark.parametrize(
    ("point", "park"),
    [((29.5300, 78.7747), "Jim Corbett National Park"), ((26.5775, 93.1711), "Kaziranga National Park")],
)
def test_india_parks_are_near_never_within(point, park):
    assert within(("world", "world-parks"), *point) == []
    assert park in near_parks(("world", "world-parks"), *point)


@pytest.mark.parametrize(
    ("point", "park"),
    [
        ((44.88, 15.62), "Plitvice Lakes National Park"),  # Plitvice Lakes, Croatia
        ((46.67, 10.18), "Swiss National Park"),  # Engadine, Switzerland
        ((47.1, 12.7), "Hohe Tauern National Park"),  # Austria
        ((44.12, 9.71), "Cinque Terre National Park"),  # Liguria, Italy
        ((50.962, 14.074), "Saxon Switzerland National Park"),  # the Bastei, Saxony, Germany
    ],
)
def test_european_national_parks_are_outlines(point, park):
    r = geocoder("world", "eur-parks", "world-parks").lookup(*point)
    assert r.within and r.within[0].name == park and r.within[0].tier == 1
    assert r.within[0].id.startswith("eea:")
    assert park not in near_parks(("world", "eur-parks", "world-parks"), *point)  # not again as a point


def test_saxon_switzerland_at_50_9_14_2_is_just_outside_the_national_park():
    # the point is in the Saxon Switzerland landscape protection area (left out: a third of Germany
    # is one), 0.7 km from the national park's rear part
    r = geocoder("world", "eur-parks", "world-parks").lookup(50.9, 14.2)
    assert not any(p.tier == 1 for p in r.within)
    assert (
        near_parks(("world", "eur-parks", "world-parks"), 50.9, 14.2)["Saxon Switzerland National Park"] < 1
    )


def test_one_park_reported_as_zones_is_one_place():
    # Hohe Tauern is a core and an outer zone in each of Carinthia, Salzburg and Tyrol
    geo = geocoder("world", "eur-parks", "world-parks")
    for name in ("Hohe Tauern National Park", "Swiss National Park"):  # and Wikidata's point merged in
        parks = [e for e in geo.find(name, kinds="park", limit=3) if e.place.name == name]
        assert [e.place.id[:4] for e in parks] == ["eea:"], name


def test_paris_is_in_no_national_park():
    found = geocoder("world", "eur-parks").lookup(48.8566, 2.3522).within  # Paris city centre
    assert not any(p.tier == 1 for p in found)


def test_the_lake_district_is_only_a_point():
    # the EEA's data has no United Kingdom since 2021: Lake District National Park stays a
    # Wikidata point in world-parks, near ("in the area of"), never within
    assert within(("world", "eur-parks", "world-parks"), 54.46, -3.09) == []
    assert "Lake District National Park" in near_parks(("world", "eur-parks", "world-parks"), 54.46, -3.09)
