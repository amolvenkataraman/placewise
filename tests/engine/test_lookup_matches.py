"""Result.matches on the world pack alone (lookup_kit): polygons are within, the provisional city
is near at its great-circle distance, an offshore country says how far out."""

import pytest
from lookup_kit import write_world

from placewise.engine import Geocoder
from placewise.geo import haversine
from placewise.model import Relation


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    return Geocoder(packs=[write_world(tmp_path_factory.mktemp("matches"))])


def test_world_fields(geo):
    r = geo.lookup(0.75, -139.75)
    assert r.matches["country"] == r.matches["admin1"]
    assert (r.matches["country"].relation, r.matches["country"].distance_km) == (Relation.WITHIN, 0.0)
    city = r.matches["city"]
    assert city.relation is Relation.NEAR and not r.city_within
    assert city.distance_km == pytest.approx(float(haversine(0.75, -139.75, 0.75, -139.5)), abs=0.01)
    assert r.matches["locality"] == city and r.city_km == city.distance_km


def test_offshore_country_and_lookup_many(geo):
    r = geo.lookup(1.05, -139.5)  # 5.6 km north of Alphaland, inside its territorial sea
    assert r.sources["country"] == "world/countries:offshore"
    m = r.matches["country"]
    assert m.relation is Relation.OFFSHORE and m.distance_km == pytest.approx(5.56, abs=0.1)
    assert geo.lookup_many([0.75, 1.05], [-139.75, -139.5]) == [geo.lookup(0.75, -139.75), r]


def test_no_place_no_match(geo):
    r = geo.lookup(-30.0, -100.0)  # open ocean
    assert r.country is None and "country" not in r.matches and "city" not in r.matches
