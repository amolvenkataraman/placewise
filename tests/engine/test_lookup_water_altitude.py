"""On or over water by altitude (placewise.engine._water.relation): "On" with no altitude, "Over"
from OVER_HEIGHT_M above the water's surface, or from AIRBORNE_M where the surface isn't known.
Over lookup_kit's world and lookup_water_kit's synthetic water pack (nothing real)."""

import math

import numpy as np
import pytest
from lookup_kit import write_world
from lookup_water_kit import write_water

from placewise.constants import water as const
from placewise.engine import Geocoder, _water
from placewise.model import Add, PlaceKind, Point, Relation

LAKE = (0.35, -139.85)  # on Lake Alpha, whose surface is at 1,897 m
OCEAN = (1.4, -139.3)  # on the Test Ocean, far offshore
BAY = (1.7, -139.7)  # on Gamma Bay
RESERVOIR = (0.125, -139.65)  # on the Southam Reservoir, whose surface elevation is unknown
POOL = (0.43, -139.78)  # on Alpha Pool, a reservoir at 420 m
LAND = (0.75, -139.45)  # Alpha City


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    root = tmp_path_factory.mktemp("water-altitude")
    return Geocoder(packs=[write_world(root), write_water(root, reservoirs=True)])


@pytest.fixture(scope="module")
def old_pack(tmp_path_factory):
    root = tmp_path_factory.mktemp("water-no-elevation")
    return Geocoder(packs=[write_world(root), write_water(root, reservoirs=True, elevation=False)])


def _relation(r):
    return r.water.relation


# --- the rule ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("altitude", "surface", "relation"),
    [
        (math.nan, 75.0, Relation.ON),  # no altitude: on, whatever the water
        (math.nan, math.nan, Relation.ON),
        (10_000.0, 75.0, Relation.OVER),  # a plane over Lake Ontario
        (1_897.0, 1_897.0, Relation.ON),  # a boat on Lake Tahoe
        (1_996.0, 1_897.0, Relation.ON),  # 99 m above it
        (1_997.0, 1_897.0, Relation.OVER),  # OVER_HEIGHT_M above it
        (3_000.0, 1_897.0, Relation.OVER),  # a plane over Tahoe
        (50.0, 0.0, Relation.ON),  # a ship's bridge on the ocean
        (200.0, 0.0, Relation.OVER),
        (-400.0, -430.0, Relation.ON),  # on the Dead Sea
        (5_000.0, math.nan, Relation.ON),  # unknown surface: could be a high lake
        (9_000.0, math.nan, Relation.OVER),  # AIRBORNE_M: in flight anywhere on Earth
    ],
)
def test_relation(altitude, surface, relation):
    assert _water.relation(altitude, surface) == relation


def test_the_constants():
    assert const.OVER_HEIGHT_M == 100 and const.AIRBORNE_M == 9_000 and const.SEA_SURFACE_M == 0
    assert not hasattr(const, "OVER_LAKE_KM2")


# --- in lookups --------------------------------------------------------------------------------


def test_without_an_altitude_all_water_is_on(geo):
    for point, label in [
        (LAKE, "On Lake Alpha"), (OCEAN, "On the Test Ocean, 76 km N of Alpha City"),
        (RESERVOIR, "On the Southam Reservoir"), (POOL, "On Alpha Pool"),
    ]:  # fmt: skip
        r = geo.lookup(*point)
        assert r.label == label and _relation(r) == Relation.ON
        assert geo.lookup(*point, altitude_m=None).to_dict() == r.to_dict()
        assert geo.lookup(*point, altitude_m=math.nan).to_dict() == r.to_dict()


def test_on_a_lake_by_its_surface(geo):
    boat = geo.lookup(*LAKE, altitude_m=1_897)
    assert boat.label == "On Lake Alpha" and _relation(boat) == Relation.ON
    plane = geo.lookup(*LAKE, altitude_m=3_000)
    assert plane.label == "Over Lake Alpha" and _relation(plane) == Relation.OVER
    # sea level would be 1,897 m below: 1,000 m is still on a lake this high
    assert _relation(geo.lookup(*LAKE, altitude_m=1_000)) == Relation.ON


def test_on_the_ocean_by_sea_level(geo):
    ship = geo.lookup(*OCEAN, altitude_m=50)
    assert ship.label == "On the Test Ocean, 76 km N of Alpha City" and _relation(ship) == Relation.ON
    plane = geo.lookup(*OCEAN, altitude_m=200)
    assert plane.label == "Over the Test Ocean, 76 km N of Alpha City"
    assert _relation(plane) == Relation.OVER
    assert geo.lookup(*BAY, altitude_m=200).label.startswith("Over Gamma Bay")


def test_a_reservoir_of_unknown_surface_is_over_only_from_airborne_height(geo):
    assert geo.lookup(*RESERVOIR, altitude_m=5_000).label == "On the Southam Reservoir"
    r = geo.lookup(*RESERVOIR, altitude_m=10_000)
    assert r.label == "Over the Southam Reservoir" and _relation(r) == Relation.OVER
    # a reservoir whose surface is known goes by it
    assert geo.lookup(*POOL, altitude_m=600).label == "Over Alpha Pool"
    assert geo.lookup(*POOL, altitude_m=500).label == "On Alpha Pool"


def test_a_pack_without_the_elevation_column_treats_every_lake_as_unknown(old_pack):
    assert old_pack.lookup(*LAKE, altitude_m=3_000).label == "On Lake Alpha"
    assert old_pack.lookup(*LAKE, altitude_m=9_500).label == "Over Lake Alpha"
    assert old_pack.lookup(*POOL, altitude_m=600).label == "On Alpha Pool"
    assert old_pack.lookup(*OCEAN, altitude_m=200).water.relation == Relation.OVER  # sea level is known


def test_the_altitude_changes_nothing_but_on_or_over(geo):
    for point in (LAKE, OCEAN, RESERVOIR, LAND):
        low, high = geo.lookup(*point).to_dict(), geo.lookup(*point, altitude_m=10_000).to_dict()
        for d in (low, high):
            d.pop("label")
            if d.get("water") is not None:
                d["water"].pop("relation")
        assert low == high
    assert geo.lookup(*LAND, altitude_m=10_000).to_dict() == geo.lookup(*LAND).to_dict()


def test_lookup_many_takes_one_altitude_or_one_per_point(geo):
    lats = np.array([LAKE[0], LAKE[0], OCEAN[0], OCEAN[0], RESERVOIR[0], LAKE[0], LAND[0], LAKE[0]])
    lons = np.array([LAKE[1], LAKE[1], OCEAN[1], OCEAN[1], RESERVOIR[1], LAKE[1], LAND[1], LAKE[1]])
    alts = [1_897, 3_000, 50, 200, 10_000, math.nan, 10_000, 3_000]
    many = geo.lookup_many(lats, lons, altitude_m=alts)
    expected = ["On", "Over", "On", "Over", "Over", "On", None, "Over"]
    assert [r.label.split()[0] if r.water else None for r in many] == expected
    # repeated points at different altitudes keep their own answers; at the same one, share it
    assert many[1] is many[7] and many[0] is not many[1]
    single = [geo.lookup(a, b, altitude_m=h) for a, b, h in zip(lats, lons, alts, strict=True)]
    assert [r.to_dict() for r in many] == [r.to_dict() for r in single]
    assert [r.label for r in geo.lookup_many(lats, lons, altitude_m=np.asarray(alts))] == [
        r.label for r in many
    ]
    one = geo.lookup_many(lats, lons, altitude_m=3_000)
    over, on = Relation.OVER, Relation.ON
    assert [_relation(r) for r in one if r.water] == [over, over, over, over, on, over, over]  # reservoir: on


def test_bad_altitudes_are_refused(geo):
    with pytest.raises(ValueError, match="2 points but 3 altitudes"):
        geo.lookup_many([0.0, 1.0], [0.0, 1.0], altitude_m=[1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="altitude"):
        geo.lookup(*LAKE, altitude_m=math.inf)


def test_water_an_override_adds_is_on_unless_airborne(tmp_path):
    from placewise.model.overrides import Layer, OverrideSet
    from placewise.overrides.engine import OverrideEngine

    rule = Add(kind=PlaceKind.WATER, name="Alpha Fountain", point=Point(*LAND), radius_m=500.0)
    overrides = OverrideEngine([OverrideSet(Layer.LOCAL, (rule,))])
    geo = Geocoder(packs=[write_world(tmp_path), write_water(tmp_path)], overrides=overrides)
    r = geo.lookup(*LAND)
    assert r.water.place.name == "Alpha Fountain" and _relation(r) == Relation.ON
    assert _relation(geo.lookup(*LAND, altitude_m=5_000)) == Relation.ON
    high = geo.lookup(*LAND, altitude_m=9_500)
    assert _relation(high) == Relation.OVER and high.label == r.label


def test_the_top_level_lookup_takes_the_altitude(geo, monkeypatch):
    import placewise
    from placewise import engine

    monkeypatch.setattr(engine, "_default", geo)
    assert placewise.lookup(*LAKE).label == "On Lake Alpha"
    assert placewise.lookup(*LAKE, altitude_m=3_000).label == "Over Lake Alpha"
