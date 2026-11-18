"""Result.matches on the real packs: inside the city, or the nearest town and how far. Public places
and open land only.

Skipped when a pack isn't built.
"""

from e2e_kit import geocoder

from placewise.model import Relation

CA = ("world", "can", "world-water")


def test_cn_tower_is_inside_toronto():
    r = geocoder(*CA).lookup(43.6426, -79.3871)
    assert r.city.name == "Toronto" and r.city_within and r.city_km == 0.0
    assert r.matches["city"].relation is Relation.WITHIN and r.locality_within


def test_prairie_point_names_the_nearest_town_with_its_distance():
    r = geocoder(*CA).lookup(52.0, -112.0)  # open Alberta prairie
    m = r.matches["city"]
    assert m.relation is Relation.NEAR and not r.city_within
    assert m.distance_km is not None and m.distance_km > 5 and r.city_km == m.distance_km
    assert r.matches["admin1"].relation is Relation.WITHIN


def test_over_lake_ontario_has_no_city_inside():
    r = geocoder(*CA).lookup(43.6, -77.9)
    assert r.label == "Over Lake Ontario"
    m = r.matches.get("city")
    assert r.city is None or (m.relation is Relation.NEAR and m.distance_km > 1)
    assert not r.city_within
