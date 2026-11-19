"""Water over the real world and world-water packs: the design page's water points (public
places only). Under the default view only the water body is asserted for disputed areas."""

import pytest
from e2e_kit import geocoder

from placewise.model import PlaceKind, Relation


@pytest.fixture(scope="module")
def geo():
    return geocoder("world", "world-water")


@pytest.fixture(scope="module")
def full():
    return geocoder("world", "usa", "can", "ind", "world-water")


def _near_water(r):
    return {n.place.name: n for n in r.near if n.place.kind == PlaceKind.WATER}


def test_on_lake_ontario(geo):
    r = geo.lookup(43.6, -77.9)
    assert r.label == "On Lake Ontario"
    assert r.water.place.name == "Lake Ontario" and r.water.relation == Relation.ON
    assert r.water.place.id == "wikidata:Q1062"
    assert 10 < r.water.distance_km < 40  # mid-lake, off the New York shore
    assert r.sources["water"] == "world-water/lakes:polygon"


def test_on_lake_tahoe(geo):
    r = geo.lookup(39.0968, -120.0324)
    assert r.label == "On Lake Tahoe"
    assert r.water.relation == Relation.ON and r.water.place.id == "wikidata:Q169962"
    assert r.country.name == "United States"  # the land answer around the lake stays
    # Global Dam Watch lists Tahoe (behind a lake-control dam): it stays a lake
    assert r.sources["water"] == "world-water/lakes:polygon" and r.water.place.codes["type"] == "lake"


def test_on_the_north_atlantic(geo):
    r = geo.lookup(50.0, -30.0)
    assert r.label == "On the North Atlantic Ocean"
    assert r.water.place.name == "North Atlantic Ocean" and r.water.relation == Relation.ON
    assert r.country is None
    assert 900 < r.water.distance_km < 1500  # the nearest coast is the Azores (Flores)


def test_arabian_sea_off_mumbai(full):
    r = full.lookup(18.90, 72.75)
    assert r.label == "On the Arabian Sea"
    assert r.water.place.name == "Arabian Sea"
    assert r.country.name == "India"  # within the territorial sea: the country stays


def test_dashashwamedh_ghat_is_beside_the_ganges(full):
    r = full.lookup(25.3069, 83.0107)
    assert r.label.startswith("Varanasi")  # a land answer: the label is unchanged
    ganges = _near_water(r)["Ganges"]
    assert ganges.relation == Relation.NEAR and ganges.distance_km < 2
    assert r.water is None


def test_on_dal_lake(full):
    lakes = full.water.layer("lakes")
    if "hydrolakes" not in lakes.sources:
        pytest.skip("Dal Lake's outline comes from HydroLAKES (built without --no-hydrolakes)")
    # the open water of the northern basin, east of Hazratbal (Wikipedia's 34°07'N 74°52'E, rounded
    # to the minute, lies between the basins, 160 m off HydroLAKES' shore: not a point on the lake)
    r = full.lookup(34.1300, 74.8540)
    assert r.water is not None and r.water.place.name == "Dal Lake"
    assert r.label == "On Dal Lake"


def test_land_answers_away_from_water_are_unchanged(full):
    land = geocoder("world", "usa", "can", "ind")
    for lat, lon in [(43.6426, -79.3871), (36.1147, -115.1728), (12.9716, 77.5946)]:
        a, b = full.lookup(lat, lon), land.lookup(lat, lon)
        assert (a.label, a.locality, a.city, a.admin1, a.country) == (
            b.label,
            b.locality,
            b.city,
            b.admin1,
            b.country,
        )
        assert a.water is None


# --- reservoirs: Global Dam Watch's where no named lake covers them, read like lakes -------------


def _has_reservoirs(pack_geo):
    if not any("reservoirs" in p for p in pack_geo.packs):
        pytest.skip("world-water built before the reservoirs layer: rebuild it")


@pytest.mark.parametrize(
    ("place", "lat", "lon", "label"),
    [
        ("Lake Mead", 36.15, -114.40, "On Lake Mead"),
        ("Tehri reservoir", 30.38, 78.48, "On the Tehri Reservoir"),
        ("Hirakud reservoir", 21.60, 83.80, "On the Hirakud Reservoir"),
    ],
)
def test_on_reservoirs(geo, place, lat, lon, label):
    _has_reservoirs(geo)
    r = geo.lookup(lat, lon)
    assert r.label == label, place
    assert r.water.relation == Relation.ON and r.water.place.codes["type"] == "reservoir"


def test_tehri_comes_from_global_dam_watch_and_search_finds_it(geo):
    _has_reservoirs(geo)
    r = geo.lookup(30.38, 78.48)
    assert r.sources["water"] == "world-water/reservoirs:polygon" and r.water.place.id.startswith("gdw:")
    assert r.country.name == "India" and r.admin1.name == "Uttarakhand"
    found = geo.find("Tehri Reservoir")
    assert found and found[0].place.id == r.water.place.id and found[0].place.kind == PlaceKind.WATER


# --- on or over, by altitude (placewise.engine._nearby.water.relation) -----------------------------------


def test_a_plane_over_lake_ontario(geo):
    r = geo.lookup(43.6, -77.9, altitude_m=10_000)
    assert r.label == "Over Lake Ontario" and r.water.relation == Relation.OVER
    assert 60 < geo.water.layer("lakes").row(_row(geo, "wikidata:Q1062"))["elevation_m"] < 90
    base = geo.lookup(43.6, -77.9).to_dict()
    high = r.to_dict()
    for d in (base, high):
        d.pop("label"), d["water"].pop("relation")
    assert base == high  # nothing else changes


def test_a_boat_on_lake_tahoe_and_a_plane_over_it(geo):
    tahoe = (39.0968, -120.0324)
    assert geo.lookup(*tahoe, altitude_m=1_897).label == "On Lake Tahoe"  # the lake is at ~1,897 m
    assert geo.lookup(*tahoe, altitude_m=1_500).label == "On Lake Tahoe"
    plane = geo.lookup(*tahoe, altitude_m=3_000)
    assert plane.label == "Over Lake Tahoe" and plane.water.relation == Relation.OVER


def test_on_or_over_the_ocean_by_sea_level(geo):
    assert geo.lookup(50.0, -30.0, altitude_m=50).label == "On the North Atlantic Ocean"
    assert geo.lookup(50.0, -30.0, altitude_m=200).label == "Over the North Atlantic Ocean"
    labels = [r.label for r in geo.lookup_many([50.0, 50.0, 43.6], [-30.0, -30.0, -77.9],
                                                 altitude_m=[11_000, float("nan"), 11_000])]  # fmt: skip
    assert labels == ["Over the North Atlantic Ocean", "On the North Atlantic Ocean", "Over Lake Ontario"]


def _row(geo, ident):
    return geo.water.layer("lakes").column("id").tolist().index(ident)
