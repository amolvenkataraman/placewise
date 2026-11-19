"""Notable places in Result.near (placewise.engine._nearby.notable) on a synthetic pack (notable_kit)."""

import pytest
from lookup_kit import write_world
from notable_kit import CENTRE, KM, NEAR_CITY, write_notable

from placewise.engine import Geocoder
from placewise.model import PlaceKind, Relation

NOTABLE_KINDS = {PlaceKind.LANDMARK, PlaceKind.BUILDING, PlaceKind.AIRPORT}


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    out = tmp_path_factory.mktemp("notable")
    return write_world(out), write_notable(out)


@pytest.fixture(scope="module")
def geo(packs):
    return Geocoder(packs=list(packs))


def notable(r):
    return [(n.place.name, round(n.distance_km, 1)) for n in r.near if n.place.id.startswith("wikidata:")]


def test_the_best_scored_win_when_more_are_in_reach(tmp_path):
    from lookup_kit import write_world as world
    from notable_kit import PLACES

    extra = [(f"Q2{i}", f"Shrine {i}", "religious_site", 0.1, CENTRE[0], CENTRE[1] + 0.1 * KM, "", "")
             for i in range(5)]  # fmt: skip
    geo = Geocoder(packs=[world(tmp_path), write_notable(tmp_path, PLACES + extra)])
    found = [name for name, _ in notable(geo.lookup(*CENTRE))]
    # score = fame x (1 - distance / reach): the chapel (0.4 x 1/3) beats the shrines (0.1 x 2/3)
    assert found == ["Alpha Tower", "Corner Chapel", "Alpha Museum"]


def test_near_lists_up_to_three_nearest_first(geo):
    r = geo.lookup(*CENTRE)
    # the tower (here), the chapel (200 m), the museum (800 m: fame 0.95 reaches 1 km);
    # not the bridge (600 m, beyond its 300 m), the airport (its own field) or the stadium (11 km)
    assert notable(r) == [("Alpha Tower", 0.0), ("Corner Chapel", 0.2), ("Alpha Museum", 0.8)]
    tower = next(n for n in r.near if n.place.name == "Alpha Tower")
    assert tower.relation == Relation.NEAR
    place = tower.place
    assert place.id == "wikidata:Q11" and place.kind == PlaceKind.LANDMARK
    assert place.codes == {"kind": "landmark", "wikidata": "Q11"} and place.aliases == ("The Tower",)
    assert place.point.lat == pytest.approx(0.30) and place.source == "synthetic"
    museum = next(n for n in r.near if n.place.name == "Alpha Museum")
    assert museum.place.kind == PlaceKind.BUILDING and museum.place.codes["kind"] == "museum"
    assert museum.compass == "N"


def test_notable_places_come_after_the_cities(geo):
    r = geo.lookup(*NEAR_CITY)
    assert [(n.place.name, n.place.kind, round(n.distance_km, 1)) for n in r.near] == [
        ("Southam", PlaceKind.LOCALITY, 5.6), ("Midway Gate", PlaceKind.LANDMARK, 0.1)
    ]  # fmt: skip


def test_reach_depends_on_fame(geo):
    # 1.5 km north of the tower: still near it (2 km), 0.7 km from the museum, too far for the chapel
    r = geo.lookup(CENTRE[0] + 1.5 * KM, CENTRE[1])
    assert notable(r) == [("Alpha Museum", 0.7), ("Alpha Tower", 1.5)]
    # 3.5 km north: nothing reaches
    assert notable(geo.lookup(CENTRE[0] + 3.5 * KM, CENTRE[1])) == []


def test_label_and_sources(geo, packs):
    for point in (CENTRE, NEAR_CITY):
        plain = Geocoder(packs=[packs[0]]).lookup(*point)
        r = geo.lookup(*point)
        assert r.label == plain.label  # the label never names a notable place
        # the cities' source when they are near, else the notable layer's
        assert r.sources["near"] == plain.sources.get("near", "world-notable/notable:radius")


def test_near_false_skips_them(geo):
    assert notable(geo.lookup(*CENTRE, near=False)) == []


def test_lookup_many_matches_lookup(geo):
    points = [CENTRE, (CENTRE[0] + 1.5 * KM, CENTRE[1]), (0.75, -139.5)]
    many = geo.lookup_many([p[0] for p in points], [p[1] for p in points])
    assert [notable(r) for r in many] == [notable(geo.lookup(*p)) for p in points]


def test_a_place_already_named_is_not_repeated(tmp_path):
    from lookup_kit import write_world as world
    from notable_kit import PLACES

    # a famous place named like the city near the point, 1.5 km away (within its 2 km reach)
    twin = [("Q30", "Southam", "landmark", 0.999, NEAR_CITY[0] - 1.5 * KM, NEAR_CITY[1], "", "")]
    geo = Geocoder(packs=[world(tmp_path), write_notable(tmp_path, PLACES + twin)])
    found = geo.notable.answer(*([v] for v in NEAR_CITY))[0][0]
    assert "Southam" in [n.place.name for n in found]
    names = [n.place.name for n in geo.lookup(*NEAR_CITY).near]
    assert names == ["Southam", "Midway Gate"]


def test_default_geocoder_opens_an_installed_notable_pack(packs):
    world, notable_pack = packs

    class FakeStore:
        def ensure(self, name):
            return world

        def installed(self):
            return {"world": ["2026.11"], "world-notable": ["2026.11"]}

        def current(self, name):
            return {"world-notable": notable_pack}[name]

    geo = Geocoder(store=FakeStore())
    assert geo.data_version == "world-2026.11+world-notable-2026.11"
    assert notable(geo.lookup(*CENTRE))[0] == ("Alpha Tower", 0.0)
