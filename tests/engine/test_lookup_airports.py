"""Result.airport: AT by the airport's size, NEAR by size, service and distance (placewise.engine.
_nearby.airports). Synthetic airports in Alphaland (lookup_kit), nothing real."""

import numpy as np
import pytest
from lookup_kit import CREATED, admin1_layer, cities_layer, countries_layer

from placewise.engine import Geocoder
from placewise.model import NearSettings, Relation, Settings
from placewise.packs import LayerData, write_pack

KM = 1 / 111.195  # degrees of latitude per km

# id, lat, lon, type, scheduled
BIG = ("ourairports:XBIG", 0.30, -139.50, "large_airport", True)
FIELD = ("ourairports:XFLD", 0.30 + 28 * KM, -139.50, "medium_airport", False)  # no airline service
COMMUTER = ("ourairports:XCOM", 0.30 + 12 * KM, -139.50, "medium_airport", True)
STRIP = ("ourairports:XSTR", 0.80, -139.20, "small_airport", True)


def _pack(root, airports, typed=True):
    columns = {"id": [a[0] for a in airports], "name": [a[0].split(":")[1] for a in airports]}
    if typed:
        columns["type"] = [a[3] for a in airports]
        columns["scheduled"] = np.array([a[4] for a in airports], dtype=bool)
    lat, lon = np.array([a[1] for a in airports]), np.array([a[2] for a in airports])
    layer = LayerData("airports", "point", columns, ("synthetic",), lat=lat, lon=lon)
    layers = [countries_layer(), admin1_layer(), cities_layer(), layer]
    return write_pack(root, "world", "2026.11", layers, created=CREATED)


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    return Geocoder(packs=[_pack(tmp_path_factory.mktemp("airports"), [BIG, FIELD, STRIP])])


def _airport(r):
    return (r.airport.place.id, r.airport.relation) if r.airport is not None else None


def test_at_radius_follows_the_size(geo):
    assert _airport(geo.lookup(0.30 + 2.3 * KM, -139.50)) == (BIG[0], Relation.AT)  # large: 2.5 km
    assert _airport(geo.lookup(FIELD[1] + 0.9 * KM, -139.50)) == (FIELD[0], Relation.AT)  # medium: 1 km
    assert _airport(geo.lookup(0.80 + 0.4 * KM, -139.20)) == (STRIP[0], Relation.AT)  # small: 0.5 km
    assert _airport(geo.lookup(0.80 + 0.7 * KM, -139.20)) == (STRIP[0], Relation.NEAR)


def test_at_any_airport_even_without_service(geo):
    r = geo.lookup(FIELD[1] - 0.5 * KM, -139.50)
    assert _airport(r) == (FIELD[0], Relation.AT) and r.airport.distance_km == pytest.approx(0.5, abs=0.01)


def test_near_skips_airports_without_scheduled_service(geo):
    r = geo.lookup(FIELD[1] + 1.5 * KM, -139.50)  # 1.5 km from the field, 29.5 km from the big one
    assert _airport(r) == (BIG[0], Relation.NEAR) and r.airport.distance_km == pytest.approx(29.5, abs=0.05)


def test_any_airport_may_be_near_when_asked(tmp_path):
    settings = Settings(near=NearSettings(airport_scheduled=False))
    geo = Geocoder(packs=[_pack(tmp_path, [BIG, FIELD])], settings=settings)
    assert _airport(geo.lookup(FIELD[1] + 1.5 * KM, -139.50)) == (FIELD[0], Relation.NEAR)


def test_a_large_airport_wins_unless_a_smaller_one_is_three_times_nearer(tmp_path):
    geo = Geocoder(packs=[_pack(tmp_path, [BIG, COMMUTER])])
    # 3 km from the commuter field, 15 km from the big one: 9 < 15
    assert _airport(geo.lookup(COMMUTER[1] + 3 * KM, -139.50)) == (COMMUTER[0], Relation.NEAR)
    # 7 km from it, 19 km from the big one: 21 > 19
    assert _airport(geo.lookup(COMMUTER[1] + 7 * KM, -139.50)) == (BIG[0], Relation.NEAR)


def test_reach_by_size(geo):
    r = geo.lookup(0.30 - 39 * KM, -139.50)  # 39 km south of the big one, out to sea
    assert _airport(r) == (BIG[0], Relation.NEAR)
    assert geo.lookup(0.30 - 41 * KM, -139.50).airport is None
    assert geo.lookup(0.80 + 11 * KM, -139.20).airport is None  # beyond the small strip's 10 km


def test_settings_narrow_the_large_reach(tmp_path):
    settings = Settings(near=NearSettings(airport_large=20.0))
    geo = Geocoder(packs=[_pack(tmp_path, [BIG])], settings=settings)
    assert geo.lookup(0.30 + 19 * KM, -139.50).airport is not None
    assert geo.lookup(0.30 + 21 * KM, -139.50).airport is None


def test_untyped_airports_read_as_medium_and_served(tmp_path):
    geo = Geocoder(packs=[_pack(tmp_path, [BIG, FIELD], typed=False)])
    assert _airport(geo.lookup(FIELD[1] + 0.9 * KM, -139.50)) == (FIELD[0], Relation.AT)
    assert _airport(geo.lookup(FIELD[1] + 1.5 * KM, -139.50)) == (FIELD[0], Relation.NEAR)
    assert geo.lookup(0.30 + 14 * KM, -139.50).airport is None  # 10 km reach for every one


def test_batch_agrees_with_single_lookups(geo):
    lats = np.array([0.30 + 2.3 * KM, FIELD[1] + 1.5 * KM, 0.80 + 0.4 * KM, 0.30 - 41 * KM])
    lons = np.array([-139.50, -139.50, -139.20, -139.50])
    many = [_airport(r) for r in geo.lookup_many(lats, lons)]
    assert many == [_airport(geo.lookup(a, b)) for a, b in zip(lats, lons, strict=True)]


def test_kind_tuning_sets_every_airports_reach(tmp_path):
    from placewise.model import Layer
    from placewise.overrides import OverrideEngine

    world = _pack(tmp_path, [BIG])
    settings = Settings(near=NearSettings(airport_large=10.0))
    point = (0.30 + 16 * KM, -139.50)  # 16 km from the large airport, beyond a 10 km reach
    assert Geocoder(packs=[world], settings=settings).lookup(*point).airport is None
    rules = {"tune": [{"kind": "airport", "near_km": 20}]}
    tune = OverrideEngine.from_documents([(Layer.APP, rules, "test")])
    r = Geocoder(packs=[world], settings=settings, overrides=tune).lookup(*point)
    assert _airport(r) == (BIG[0], Relation.NEAR)
