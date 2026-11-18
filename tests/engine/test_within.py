"""Parks in Result.within and Result.near (placewise.engine._within) on synthetic packs (parks_kit)."""

import dataclasses

import numpy as np
import pytest
from lookup_kit import write_world
from parks_kit import write_parks

from placewise.engine import Geocoder, _results
from placewise.model import LabelSettings, PlaceKind, Point, Relation, Settings


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


def test_generic_names_are_never_within_or_near(geo):
    """Packs built before the build dropped them still have "Open Space" and "Unknown Park" rows."""
    assert geo.lookup(0.305, -139.195).within == ()
    assert parks_near(geo.lookup(0.315, -139.195)) == []  # 0.5 km from it: near, were it a name
    assert parks_near(geo.lookup(2.11, -139.9)) == []  # 1.1 km from a generic point park


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


def test_label_names_a_national_or_state_park_instead_of_state_and_country(geo, packs):
    r = geo.lookup(0.75, -139.75)  # Alpha City's locality, in the preserve (tier 1)
    assert r.label == "Alpha City, Alpha Preserve"
    plain = Geocoder(packs=[packs[0]]).lookup(0.75, -139.75)
    assert plain.label == "Alpha City, North Province, Alphaland"
    off = Geocoder(packs=list(packs), settings=Settings(label=LabelSettings(parks=False)))
    assert off.lookup(0.75, -139.75).label == plain.label  # label.parks = false: the plain rule


def test_label_park_rule_skips_local_parks_and_national_forests(geo, packs):
    plain = Geocoder(packs=[packs[0]])
    for point in [(0.105, -139.295), (0.225, -139.075), (0.57, -139.75)]:  # local, regional, forest only
        assert geo.lookup(*point).within
        assert geo.lookup(*point).label == plain.lookup(*point).label


def test_label_park_alone_without_a_locality(geo):
    r = geo.lookup(0.75, -139.75)
    bare = dataclasses.replace(r, locality=None, city=None)
    assert _results.compose(geo.settings.label, bare) == "Alpha Preserve"
    # no locality: the city leads only when its point lies in the park's box, else it would name a
    # town outside the park (Alpha City's point is 22 km east of the preserve)
    far = dataclasses.replace(r, locality=None)
    assert _results.compose(geo.settings.label, far) == "Alpha Preserve"
    inside = dataclasses.replace(r.city, name="Preserve Village", point=Point(0.75, -139.75))
    assert _results.compose(geo.settings.label, dataclasses.replace(far, city=inside)) == (
        "Preserve Village, Alpha Preserve"
    )
    city_style = LabelSettings(style="city")
    assert _results.compose(city_style, dataclasses.replace(r, locality=None)) == "Alpha City, Alpha Preserve"
    same = dataclasses.replace(r, locality=dataclasses.replace(r.locality, name="Alpha Preserve"))
    assert _results.compose(geo.settings.label, same) == "Alpha Preserve"  # no "X, X"


def test_without_park_packs_nothing_changes(packs, geo):
    plain = Geocoder(packs=[packs[0]])
    for point in [(0.75, -139.75), (0.97, -139.75), (2.25, -139.62)]:
        a, b = plain.lookup(*point), geo.lookup(*point)
        assert a.within == () and "within" not in a.sources
        assert b.city == a.city
        assert b.label == a.label or (b.within and b.within[0].tier <= 2)  # the park label rule
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
