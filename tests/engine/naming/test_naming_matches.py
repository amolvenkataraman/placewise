"""Result.matches on the synthetic country packs (naming_kit): inside the place, or a fallback
chosen by rule, with its distance."""

import pytest

from placewise.geo import haversine
from placewise.model import Relation


def rel(r, field):
    m = r.matches[field]
    return m.relation, m.distance_km


def test_polygon_fields_are_within(geo):
    r = geo.lookup(10.52, -149.28)  # Emeryville, an incorporated place
    for field in ("country", "admin1", "admin2", "locality", "city"):
        assert rel(r, field) == (Relation.WITHIN, 0.0), field
    assert r.city_within and r.locality_within and r.city_km == 0.0


def test_postal_and_metro_cities_are_near_with_their_distance(geo):
    r = geo.lookup(10.27, -149.85)  # Paradise CDP, addressed Las Vegas
    assert r.matches["sublocality"].relation is Relation.WITHIN  # Paradise itself
    relation, km = rel(r, "locality")
    assert relation is Relation.NEAR and km > 0 and not r.locality_within
    r = geo.lookup(10.45, -149.2)  # unincorporated, no ZCTA: the metro's principal city
    relation, km = rel(r, "city")
    assert relation is Relation.NEAR and km > 1 and r.city_km == km and "locality" not in r.matches


def test_shore_snap_is_near_within_the_margin(geo):
    r = geo.lookup(10.75, -149.495)  # 0.5 km east of Kings County, in the gap
    relation, km = rel(r, "admin2")
    assert relation is Relation.NEAR and km == pytest.approx(0.5, abs=0.15)


def test_geonames_fallback_city_is_near_by_great_circle(geo):
    r = geo.lookup(10.15, -149.05)  # rural, 60 km from San Francisco: Farview by score
    assert r.sources["city"] == "world/cities:score"
    relation, km = rel(r, "city")
    assert relation is Relation.NEAR and km > 0
    assert km == pytest.approx(float(haversine(10.15, -149.05, r.city.point.lat, r.city.point.lon)), abs=0.01)


def test_metro_principal_city_distance_is_to_its_outline(geo):
    r = geo.lookup(10.45, -149.2)  # unincorporated: San Francisco (10.6 .. 10.9 N) stands for it
    assert r.sources["city"] == "us/places:metro"
    assert rel(r, "city") == (Relation.NEAR, pytest.approx(0.15 * 111.195, abs=0.2))
    r = geo.lookup(10.25, -148.6)  # Pickering rolls up to Toronto (10.5 .. 11 N)
    assert r.sources["city"] == "ca/csd:metro"
    assert rel(r, "city") == (Relation.NEAR, pytest.approx(0.25 * 111.195, abs=0.2))
    assert rel(r, "locality") == (Relation.WITHIN, 0.0) and not r.city_within
