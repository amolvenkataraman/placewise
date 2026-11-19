"""Town and city outlines in lookups (placewise.engine.naming.towns), on lookup_kit's invented
world with towns_kit's world-towns pack."""

import dataclasses

import pytest
from lookup_kit import write_world
from towns_kit import TOWNS, write_towns

from placewise.constants import towns as towns_const
from placewise.engine import Geocoder
from placewise.model import Relation

IN_TINYVILLE = (0.75, -139.365)  # in Tinyville's outline, 1.7 km from it, 15 km from Alpha City
IN_ALPHA = (0.70, -139.45)
OUTSIDE = [(0.30, -139.60), (0.45, -139.80), (0.95, -139.10), (0.25, -138.97)]
TOWNS_SOURCE = "world-towns/towns:polygon"
SCORE_SOURCE = "world/cities:score"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return write_world(tmp_path_factory.mktemp("towns-world"))


@pytest.fixture(scope="module")
def plain(world):
    return Geocoder(packs=[world])


@pytest.fixture(scope="module")
def geo(world, tmp_path_factory):
    return Geocoder(packs=[world, write_towns(tmp_path_factory.mktemp("towns"))])


def same(a, b):
    """Results equal but for data_version (it names the packs)."""
    return dataclasses.replace(a, data_version="") == dataclasses.replace(b, data_version="")


def test_a_town_outline_names_the_town_the_score_passed_over(geo, plain):
    before = plain.lookup(*IN_TINYVILLE)
    assert before.locality.name == "Alpha City"  # the bigger city scores higher from 15 km
    r = geo.lookup(*IN_TINYVILLE)
    assert r.city.name == r.locality.name == "Tinyville"
    assert r.city.id == "geonames:2" and r.city.point is not None  # the world pack's own place
    assert r.sources["city"] == r.sources["locality"] == TOWNS_SOURCE
    assert r.matches["city"].relation == r.matches["locality"].relation == Relation.WITHIN
    assert r.label == "Tinyville, North Province, Alphaland"


def test_inside_a_city_outline_its_city_is_within(geo):
    r = geo.lookup(*IN_ALPHA)
    assert r.city.name == r.locality.name == "Alpha City"
    assert r.sources["city"] == r.sources["locality"] == TOWNS_SOURCE
    assert r.matches["city"].relation == Relation.WITHIN and r.matches["city"].distance_km == 0


def test_a_suburb_keeps_its_name_and_rolls_up_into_the_city(world, tmp_path):
    # Alpha City's outline stretched over Tinyville: the score's Tinyville stays the locality, and
    # (1,000 people beside 1,000,000) Alpha City is its city
    rows = [((0.60, -139.60, 0.90, -139.30), *TOWNS[0][1:])]
    geo = Geocoder(packs=[world, write_towns(tmp_path, rows)])
    r = geo.lookup(0.75, -139.35)
    assert (r.locality.name, r.city.name) == ("Tinyville", "Alpha City")
    assert r.sources["locality"] == SCORE_SOURCE and r.sources["city"] == TOWNS_SOURCE
    assert r.matches["locality"].relation == Relation.NEAR and r.matches["city"].relation == Relation.WITHIN
    assert "Alpha City" not in [n.place.name for n in r.near]  # it is the city, not a place near


def test_a_place_big_enough_stays_its_own_city(world, tmp_path, monkeypatch):
    import placewise.constants.naming as naming_const

    monkeypatch.setattr(naming_const, "CITY_KEEP_POPULATION", 500)  # Tinyville (1,000) keeps itself
    rows = [((0.60, -139.60, 0.90, -139.30), *TOWNS[0][1:])]
    r = Geocoder(packs=[world, write_towns(tmp_path, rows)]).lookup(0.75, -139.35)
    assert (r.locality.name, r.city.name) == ("Tinyville", "Tinyville")
    assert r.sources["city"] == SCORE_SOURCE


def test_outside_the_outlines_nothing_changes(geo, plain):
    for lat, lon in OUTSIDE:
        assert same(geo.lookup(lat, lon), plain.lookup(lat, lon))


def test_an_outline_of_another_country_is_never_used(geo, plain):
    # Zed Harbour's outline says XA, but the ground is Betaland's
    assert same(geo.lookup(0.5, -138.05), plain.lookup(0.5, -138.05))
    # Gamma Port's outline is XC's: under Alphaland's worldview the island is XA's
    assert geo.lookup(2.25, -139.75).sources["city"] == TOWNS_SOURCE
    assert same(geo.lookup(2.25, -139.75, worldview="xa"), plain.lookup(2.25, -139.75, worldview="xa"))


def test_an_outline_whose_place_is_missing_is_skipped(geo, plain):
    assert same(geo.lookup(0.12, -139.92), plain.lookup(0.12, -139.92))


def test_countries_with_their_own_packs_are_left_out(world, tmp_path, monkeypatch):
    monkeypatch.setattr(towns_const, "LEFT_OUT", ("XA",))
    geo = Geocoder(packs=[world, write_towns(tmp_path)])
    assert same(geo.lookup(*IN_TINYVILLE), Geocoder(packs=[world]).lookup(*IN_TINYVILLE))


def test_batches_agree_with_single_lookups(geo):
    points = [IN_TINYVILLE, IN_ALPHA, *OUTSIDE, (2.25, -139.75)]
    many = geo.lookup_many([p[0] for p in points], [p[1] for p in points])
    assert all(m == geo.lookup(*p) for m, p in zip(many, points, strict=True))
