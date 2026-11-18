"""Parks in Result.within and Result.near (placewise.engine._within) on synthetic packs (parks_kit)."""

import dataclasses

import numpy as np
import pytest
from lookup_kit import write_world
from parks_kit import write_parks

from placewise.engine import Geocoder
from placewise.model import LabelSettings, PlaceKind, Relation, Settings


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    out = tmp_path_factory.mktemp("parks")
    return (write_world(out), *write_parks(out))


@pytest.fixture(scope="module")
def geo(packs):
    return Geocoder(packs=list(packs))


def parks_near(r):
    return [(n.place.name, round(n.distance_km, 1)) for n in r.near if n.place.kind == PlaceKind.PARK]


def test_within_lists_every_park_most_significant_first(geo):
    r = geo.lookup(0.75, -139.75)  # in the preserve, the national park and the forest
    assert [p.name for p in r.within] == ["Alpha Preserve", "Alpha National Park", "North Forest"]
    assert [p.tier for p in r.within] == [1, 1, 2]
    park = r.within[1]
    assert park.id == "nps:ALPH" and park.kind == PlaceKind.PARK
    assert park.codes["designation"] == "National Park" and park.aliases == ("Alpha NP",)
    assert park.source == "synthetic"
    assert r.sources["within"] == "usa-parks/parks_national:polygon"
    assert parks_near(r) == []  # nothing it is inside is also "near"


def test_parcels_of_one_park_are_one_place(geo):
    for lat in (0.105, 0.125):
        r = geo.lookup(lat, -139.295)
        assert [p.id for p in r.within] == ["pad-us:xa:lp:town-green"]
    r = geo.lookup(0.115, -139.295)  # between the parcels: local parks are named only inside
    assert r.within == () and parks_near(r) == []


def test_near_reaches_by_tier(geo):
    r = geo.lookup(0.97, -139.75)  # 2.2 km north of the forest, 7.8 km north of the national park
    assert r.within == ()
    assert parks_near(r) == [("North Forest", 2.2), ("Alpha National Park", 7.8), ("Alpha Preserve", 18.9)]
    near = next(n for n in r.near if n.place.name == "North Forest")
    assert near.relation == Relation.NEAR and near.place.tier == 2
    # 27.8 km from the forest (tier 2: 10 km) and 33 km from the park (tier 1: 25 km): neither
    assert parks_near(geo.lookup(0.3, -139.75)) == []
    assert parks_near(geo.lookup(0.255, -139.075)) == [("Marsh Conservation Area", 0.6)]
    assert parks_near(geo.lookup(0.26, -139.075)) == []  # 1.1 km: past tier 3's 1 km


def test_parks_follow_the_notable_cities_in_near(geo):
    r = geo.lookup(0.97, -139.5)
    kinds = [n.place.kind for n in r.near]
    assert PlaceKind.PARK in kinds and kinds == sorted(kinds, key=lambda k: k == PlaceKind.PARK)
    assert geo.lookup(0.97, -139.75, near=False).near == ()


def test_near_distances_follow_the_settings(packs):
    settings = Settings(near=dataclasses.replace(Settings().near, park_tier2=1.0))
    r = Geocoder(packs=list(packs), settings=settings).lookup(0.97, -139.75)
    assert parks_near(r) == [("Alpha National Park", 7.8), ("Alpha Preserve", 18.9)]


def test_point_parks_are_near_never_within(geo):
    r = geo.lookup(2.25, -139.62)  # 2.2 km from the point of a park with a 5 km radius
    assert r.within == ()
    assert parks_near(r) == [("Gamma National Park", 0.0)]  # in the area of the park
    assert r.sources["near"] == "world-parks/park_points:radius"
    gamma = r.near[-1].place
    assert gamma.id == "wikidata:Q1" and gamma.point.lat == pytest.approx(2.25) and gamma.tier == 1
    assert gamma.bbox is None
    assert parks_near(geo.lookup(2.25, -139.85)) == [("Gamma National Park", 22.8)]  # 27.8 - 5 km
    assert parks_near(geo.lookup(2.25, -139.9)) == []  # 33.4 - 5 km: past 25 km
    r = geo.lookup(2.4, -139.85)  # 5.6 km from a sanctuary known only by its point (tier 2: 10 km)
    assert ("Gamma Sanctuary", 5.6) in parks_near(r)


def test_label_template_can_name_the_park(packs):
    settings = Settings(label=LabelSettings(template="{within}, {admin1}"))
    r = Geocoder(packs=list(packs), settings=settings).lookup(0.75, -139.75)
    assert r.label == "Alpha Preserve, North Province"
    plain = Geocoder(packs=[packs[0]]).lookup(0.75, -139.75).label
    assert Geocoder(packs=list(packs)).lookup(0.75, -139.75).label == plain  # the default label is unchanged


def test_without_park_packs_nothing_changes(packs, geo):
    plain = Geocoder(packs=[packs[0]])
    for point in [(0.75, -139.75), (0.97, -139.75), (2.25, -139.62)]:
        a, b = plain.lookup(*point), geo.lookup(*point)
        assert a.within == () and "within" not in a.sources
        assert b.label == a.label and b.city == a.city
        assert [n for n in b.near if n.place.kind != PlaceKind.PARK] == list(a.near)


def test_lookup_many_equals_lookup(geo):
    rng = np.random.default_rng(3)
    lats = np.concatenate([rng.uniform(0, 1, 60), rng.uniform(2, 2.5, 20), [0.75, 0.97, 0.125, 2.25]])
    lons = np.concatenate([rng.uniform(-140, -139, 60), rng.uniform(-140, -139.5, 20), [-139.75] * 2,
                           [-139.295, -139.62]])  # fmt: skip
    many = geo.lookup_many(lats, lons)
    for r, lat, lon in zip(many, lats, lons, strict=True):
        assert r == geo.lookup(lat, lon)


def test_default_geocoder_opens_installed_park_packs(packs):
    world, outlines, points = packs

    class FakeStore:
        def ensure(self, name):
            return world

        def installed(self):
            return {"world": ["2026.11"], "usa-parks": ["2026.11"], "world-parks": ["2026.11"]}

        def current(self, name):
            return {"usa-parks": outlines, "world-parks": points}[name]

    geo = Geocoder(store=FakeStore())
    assert geo.data_version == "world-2026.11+usa-parks-2026.11+world-parks-2026.11"
    assert geo.lookup(0.75, -139.75).within[0].name == "Alpha Preserve"


# --- the places-only lookup behind search's context ----------------------------------------------

PLACE_FIELDS = ("country", "admin1", "admin2", "city", "locality", "sublocality", "borough", "postal")
POINTS = ([0.75, 0.105, 0.97, 2.25, -10.0], [-139.75, -139.295, -139.75, -139.75, -160.0])


def _places(results):
    return [({f: getattr(r, f) for f in PLACE_FIELDS}, r.cc) for r in results]


def test_lookup_places_skips_parks_when_no_rule_can_read_them(packs, monkeypatch):
    geo = Geocoder(packs=list(packs))
    full = geo.lookup_many(*POINTS, near=False)

    def no_parks(*args, **kwargs):
        raise AssertionError("the parks step ran")

    monkeypatch.setattr(geo.parks, "answer", no_parks)
    assert _places(geo._lookup_places(*POINTS)) == _places(full)


def test_lookup_places_reads_parks_for_a_city_rule_naming_a_park(packs):
    from placewise.model import AreaSelector, CityRule
    from placewise.model.overrides import Layer, OverrideSet
    from placewise.overrides.engine import OverrideEngine

    rule = CityRule(within=AreaSelector(place="nps:ALPH"), city="Parkville")
    geo = Geocoder(packs=list(packs), overrides=OverrideEngine([OverrideSet(Layer.LOCAL, (rule,))]))
    light = geo._lookup_places(*POINTS)
    assert light[0].city.name == "Parkville"
    assert _places(light) == _places(geo.lookup_many(*POINTS, near=False))
