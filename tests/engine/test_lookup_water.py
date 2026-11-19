"""Water in lookups (placewise.engine._water) over lookup_kit's world and a synthetic
world-water pack (lookup_water_kit): on a sea or lake, and near one or a river."""

import numpy as np
import pytest
from lookup_kit import write_world
from lookup_water_kit import write_water

from placewise.constants import water as const
from placewise.engine import Geocoder, _water
from placewise.model import PlaceKind, Relation

KM_PER_DEG = 111.195  # on the mean sphere


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    root = tmp_path_factory.mktemp("water")
    return write_world(root), write_water(root)


@pytest.fixture(scope="module")
def land(packs):
    return Geocoder(packs=[packs[0]])


@pytest.fixture(scope="module")
def geo(packs):
    return Geocoder(packs=list(packs))


def _near(r, kind=PlaceKind.WATER):
    return {n.place.name: n for n in r.near if n.place.kind == kind}


# --- on a lake ---------------------------------------------------------------------------------


def test_on_a_lake_names_it_with_the_distance_to_shore(geo, land):
    r = geo.lookup(0.35, -139.85)
    assert r.label == "On Lake Alpha"
    assert r.water.place.name == "Lake Alpha" and r.water.place.kind == PlaceKind.WATER
    assert r.water.relation == Relation.ON
    assert r.water.distance_km == pytest.approx(0.05 * KM_PER_DEG, rel=0.01)  # to the nearest shore
    assert r.water.compass in {"N", "S", "E", "W"}
    assert r.water.place.id == "hydrolakes:1" and r.water.place.codes["type"] == "lake"
    assert r.sources["water"] == "world-water/lakes:polygon"
    # the land answer around it stays
    base = land.lookup(0.35, -139.85)
    assert (r.country.id, r.admin1.id, r.city.id) == (base.country.id, base.admin1.id, base.city.id)


def test_by_the_lake_shore_the_land_answer_stays_and_the_lake_is_near(geo, land):
    # 55 m inside the outline: within HydroLAKES' shore margin, so on the shore, not on the lake
    r = geo.lookup(0.3005, -139.85)
    assert r.water is None and r.label == land.lookup(0.3005, -139.85).label
    lake = _near(r)["Lake Alpha"]
    assert lake.relation == Relation.NEAR and lake.distance_km == pytest.approx(0.0556, rel=0.02)


def test_near_a_lake_depends_on_its_size(geo):
    near = _near(geo.lookup(0.29, -139.85))  # 1.1 km south of a 123 km² lake: within 2 km
    assert near["Lake Alpha"].distance_km == pytest.approx(0.01 * KM_PER_DEG, rel=0.01)
    assert "Lake Alpha" not in _near(geo.lookup(0.27, -139.85))  # 3.3 km: too far


def test_natural_earth_lakes_need_a_wider_shore_margin(tmp_path):
    world, water = write_world(tmp_path), write_water(tmp_path / "ne", lake_source="naturalearth")
    r = Geocoder(packs=[world, water]).lookup(0.303, -139.85)  # 0.33 km inside: NE is ~1 km off
    assert r.water is None and "Lake Alpha" in _near(r)


# --- on the sea --------------------------------------------------------------------------------


def test_far_offshore_is_on_the_ocean_with_the_reference_kept(geo, land):
    base = land.lookup(1.4, -139.3)
    assert base.label == "Offshore, 76 km N of Alpha City"
    r = geo.lookup(1.4, -139.3)
    assert r.label == "On the Test Ocean, 76 km N of Alpha City"
    assert r.water.place.name == "Test Ocean" and r.water.relation == Relation.ON
    assert r.water.distance_km == pytest.approx(base.water.distance_km, rel=1e-9)  # shore = coast
    assert r.water.compass == "S"
    assert r.water.place.aliases == ("Testic Ocean",)
    assert r.sources["water"] == "world-water/marine:polygon"
    # the nearest country, which `water` used to hold, moves to `near`
    offshore = [n for n in r.near if n.relation == Relation.OFFSHORE]
    assert [n.place.id for n in offshore] == ["iso:XA"]
    assert r.country is None


def test_a_bay_drawn_over_the_ocean_answers_first(geo):
    r = geo.lookup(1.7, -139.7)
    assert r.water.place.name == "Gamma Bay"
    assert r.label.startswith("On Gamma Bay")  # bays take no article


def test_within_territorial_waters_the_country_stays_and_the_label_names_the_sea(geo, land):
    base = land.lookup(1.1, -139.5)
    assert base.country.id == "iso:XA" and base.label != "Offshore"
    r = geo.lookup(1.1, -139.5)
    assert r.label == "On the Test Ocean"
    assert r.country.id == "iso:XA" and r.admin1.id == base.admin1.id
    assert r.water.distance_km == pytest.approx(0.1 * KM_PER_DEG, rel=0.01)


def test_beside_the_coast_is_land_with_the_sea_near(geo, land):
    for lat in (1.005, 0.98):  # just off the drawn coast (within the margin), and just inland
        r = geo.lookup(lat, -139.5)
        assert r.water is None and r.label == land.lookup(lat, -139.5).label
        sea = _near(r)["Test Ocean"]
        # edges are great-circle arcs, which bow a little poleward of the drawn parallel
        assert sea.distance_km == pytest.approx(abs(lat - 1.0) * KM_PER_DEG, rel=0.03)


def test_far_from_every_country_the_shore_distance_is_still_measured(geo):
    r = geo.lookup(-10.0, -160.0)
    assert r.label == "On the Far Sea"  # no country or city within reach: no reference
    assert r.water.distance_km > 2000


def test_sea_in_no_polygon_takes_the_nearest_one(geo):
    r = geo.lookup(5.1, -140.0)  # 11 km beyond the ocean's drawn edge
    assert r.water.place.name == "Test Ocean"
    assert r.sources["water"] == "world-water/marine:nearest"


def test_open_water_beyond_every_marine_polygon_stays_offshore(geo):
    r = geo.lookup(-30.0, -100.0)
    assert r.water is None and r.label == "Offshore"


# --- rivers ------------------------------------------------------------------------------------


def test_beside_a_river(geo):
    near = _near(geo.lookup(0.61, -139.8))
    river = near["Alpha River"]
    assert river.relation == Relation.NEAR
    assert river.distance_km == pytest.approx(0.01 * KM_PER_DEG, rel=0.01)
    assert river.place.codes["type"] == "river"
    assert "Alpha River" not in _near(geo.lookup(0.64, -139.8))  # 4.4 km


# --- consistency -------------------------------------------------------------------------------


# --- reservoirs (Global Dam Watch), read like lakes ---------------------------------------------


@pytest.fixture(scope="module")
def dams(tmp_path_factory):
    root = tmp_path_factory.mktemp("water-reservoirs")
    return Geocoder(packs=[write_world(root), write_water(root, reservoirs=True)])


def test_on_a_reservoir_like_on_a_lake(dams):
    r = dams.lookup(0.125, -139.65)
    assert r.label == "On the Southam Reservoir"
    assert r.water.relation == Relation.ON and r.water.place.id == "gdw:2"
    assert r.water.place.codes["type"] == "reservoir"
    assert r.water.distance_km == pytest.approx(0.025 * KM_PER_DEG, abs=0.05)
    assert r.sources["water"] == "world-water/reservoirs:polygon"
    assert r.country.name == "Alphaland"


def test_near_a_reservoir_like_near_a_lake(dams):
    r = dams.lookup(0.155, -139.65)  # 0.56 km north of its shore; lakes of 10 km²+ are near within 1 km
    assert r.water is None
    assert _near(r)["Southam Reservoir"].distance_km == pytest.approx(0.005 * KM_PER_DEG, abs=0.02)
    assert "Southam Reservoir" not in _near(dams.lookup(0.17, -139.65))  # 2.2 km


def test_a_lake_answers_before_a_reservoir_drawn_over_it(dams):
    r = dams.lookup(0.37, -139.82)
    assert r.water.place.name == "Lake Alpha" and r.sources["water"] == "world-water/lakes:polygon"
    assert dams.lookup(0.43, -139.78).water.place.name == "Alpha Pool"  # outside the lake


def test_lookup_many_equals_lookup(geo):
    lats = np.array([0.35, 0.3005, 0.29, 1.4, 1.7, 1.1, 1.005, -10.0, 5.1, -30.0, 0.61, 0.75])
    lons = np.array([-139.85, -139.85, -139.85, -139.3, -139.7, -139.5, -139.5, -160.0, -140.0,
                     -100.0, -139.8, -139.45])  # fmt: skip
    many = geo.lookup_many(lats, lons)
    assert [r.to_dict() for r in many] == [
        geo.lookup(a, b).to_dict() for a, b in zip(lats, lons, strict=True)
    ]


PLACE_FIELDS = ("country", "admin1", "admin2", "city", "locality", "sublocality", "borough", "postal")


def test_lookup_places_matches_lookup_many_without_reading_water(packs, monkeypatch):
    geo = Geocoder(packs=list(packs))
    lats = np.array([0.35, 0.3005, 0.29, 1.4, 1.7, 1.1, 1.005, -10.0, 5.1, -30.0, 0.61, 0.75])
    lons = np.array([-139.85, -139.85, -139.85, -139.3, -139.7, -139.5, -139.5, -160.0, -140.0,
                     -100.0, -139.8, -139.45])  # fmt: skip
    full = geo.lookup_many(lats, lons, near=False)

    def no_water(*args, **kwargs):
        raise AssertionError("the water step ran")

    monkeypatch.setattr(geo.water, "answer", no_water)
    light = geo._lookup_places(lats, lons)
    for a, b in zip(light, full, strict=True):
        assert {f: getattr(a, f) for f in PLACE_FIELDS} == {f: getattr(b, f) for f in PLACE_FIELDS}
        assert (a.cc, a.regions) == (b.cc, b.regions)
        assert a.airport is None and (a.water is None or a.water.place.kind != PlaceKind.WATER)


def test_land_far_from_water_is_unchanged(geo, land):
    for lat, lon in [(0.75, -139.45), (0.25, -138.97), (2.25, -139.75)]:
        assert geo.lookup(lat, lon).to_dict() == land.lookup(lat, lon).to_dict() | {
            "data_version": "world-2026.11+world-water-2026.11"
        }


def test_the_default_geocoder_opens_an_installed_water_pack(packs):
    world, water = packs

    class FakeStore:
        def ensure(self, name):
            return world

        def installed(self):
            return {"world": ["2026.11"], const.PACK: ["2026.11"]}

        def current(self, name):
            assert name == const.PACK
            return water

    geo = Geocoder(store=FakeStore())
    assert geo.lookup(0.35, -139.85).label == "On Lake Alpha"


@pytest.mark.parametrize(
    ("relation", "name", "kind", "phrase"),
    [
        (Relation.ON, "North Atlantic Ocean", "ocean", "On the North Atlantic Ocean"),
        (Relation.OVER, "North Atlantic Ocean", "ocean", "Over the North Atlantic Ocean"),
        (Relation.ON, "Arabian Sea", "sea", "On the Arabian Sea"),
        (Relation.OVER, "Gulf of Mexico", "gulf", "Over the Gulf of Mexico"),
        (Relation.OVER, "Persian Gulf", "gulf", "Over the Persian Gulf"),
        (Relation.OVER, "Hudson Bay", "bay", "Over Hudson Bay"),
        (Relation.OVER, "Bay of Bengal", "bay", "Over the Bay of Bengal"),
        (Relation.OVER, "Lake Ontario", "lake", "Over Lake Ontario"),
        (Relation.ON, "Lake Tahoe", "lake", "On Lake Tahoe"),
        (Relation.ON, "Hirakud Reservoir", "reservoir", "On the Hirakud Reservoir"),
        (Relation.OVER, "Kattegat", "strait", "Over the Kattegat"),
        (Relation.OVER, "Øresund", "strait", "Over the Øresund"),
        (Relation.OVER, "Puget Sound", "sound", "Over Puget Sound"),
    ],
)
def test_phrases(relation, name, kind, phrase):
    assert _water.phrase(relation, name, kind) == phrase
