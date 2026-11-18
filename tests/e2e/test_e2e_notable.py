"""Notable places on the real world-notable pack: public places only.

Skipped when a pack isn't built (`uv run python -m packbuild.notable`).
"""

import pytest
from e2e_kit import geocoder, require_packs

PACKS = ("world", "world-notable")


def near_notable(lat, lon):
    return [
        n.place.name for n in geocoder(*PACKS).lookup(lat, lon).near if n.place.id.startswith("wikidata:")
    ]


@pytest.mark.parametrize(
    ("point", "place"),
    [
        ((43.6426, -79.3871), "CN Tower"),  # at its base, Toronto
        ((43.6453, -79.3806), "Union Station"),  # Front Street, Toronto
        ((48.8584, 2.2945), "Eiffel Tower"),
        ((37.8199, -122.4783), "Golden Gate Bridge"),  # mid-span
        ((35.6595, 139.7005), "Shibuya scramble crossing"),
        ((27.1751, 78.0421), "Taj Mahal"),
        ((18.9220, 72.8347), "Gateway of India"),
        ((19.1334, 72.9133), "Indian Institute of Technology Bombay"),  # Powai campus
        ((43.4700, -80.5440), "University of Waterloo"),  # the campus ring road
    ],
)
def test_near_a_landmark(point, place):
    assert place in near_notable(*point)


def test_a_world_famous_place_reaches_farther():
    # Union Station is 600 m from the CN Tower, which (fame 0.99+) reaches 2 km
    assert "CN Tower" in near_notable(43.6453, -79.3806)


def test_one_union_station_not_two():
    names = near_notable(43.6453, -79.3806)
    assert names.count("Union Station") == 1 and "Union" not in names  # the subway's "Union" is merged


def test_the_label_is_unchanged():
    plain = geocoder("world").lookup(43.6426, -79.3871)
    with_notable = geocoder(*PACKS).lookup(43.6426, -79.3871)
    assert with_notable.label == plain.label == "Toronto, Ontario, Canada"


def test_nothing_notable_in_the_countryside():
    assert near_notable(44.5, -78.9) == []  # farmland in the Kawarthas, Ontario


@pytest.mark.parametrize(
    ("name", "alias"),
    [
        ("Indian Institute of Technology Bombay", "IIT Bombay"),
        ("Shibuya scramble crossing", "Shibuya Crossing"),
        ("Union Station", "Toronto Union Station"),
        ("University of Waterloo", "UW"),
    ],
)
def test_search_names_are_in_the_pack(name, alias):
    from placewise.packs import open_pack

    layer = open_pack(require_packs("world-notable")[0])["notable"]
    names = layer.column("name").tolist()
    rows = [i for i, n in enumerate(names) if n == name]
    assert any(alias in (layer.value("aliases", i) or "").split("|") for i in rows)


def test_codes_are_in_the_pack():
    from placewise.packs import open_pack

    layer = open_pack(require_packs("world-notable")[0])["notable"]
    ids = layer.column("id").tolist()
    pearson = layer.row(ids.index("wikidata:Q242066"))
    assert (pearson["kind"], pearson["iata"], pearson["icao"]) == ("airport", "YYZ", "CYYZ")
    csmt = layer.row(ids.index("wikidata:Q235884"))  # Chhatrapati Shivaji Maharaj Terminus, Mumbai
    assert csmt["kind"] == "station" and csmt["station_code"] == "CSMT"
    harvard = layer.row(ids.index("wikidata:Q13371"))
    assert harvard["kind"] == "university" and harvard["ipeds"] == "166027"
