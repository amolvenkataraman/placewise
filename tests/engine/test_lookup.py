"""Point lookup on a tiny synthetic pack (lookup_kit): rules, worldviews, hooks, batch == single."""

import dataclasses

import numpy as np
import pytest
from lookup_kit import write_world

from placewise.constants import lookup as const
from placewise.engine import Geocoder
from placewise.geo import haversine
from placewise.model import PlaceKind, Relation, Settings, WorldviewSettings
from placewise.packs import open_pack


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return write_world(tmp_path_factory.mktemp("lookup"))


@pytest.fixture(scope="module")
def geo(world):
    return Geocoder(packs=[world])


def score(population, km):
    return max(population, const.CITY_MIN_POPULATION) ** const.CITY_SCORE_ALPHA / (
        km + const.CITY_SCORE_D0_KM
    )


# --- country and admin1 -----------------------------------------------------------------------


def test_polygon_hit(geo):
    r = geo.lookup(0.75, -139.45)
    assert r.country.id == "iso:XA" and r.country.kind == PlaceKind.COUNTRY
    assert r.country.codes["iso2"] == "XA" and r.cc == "XA"
    assert r.admin1.id == "iso:XA-N" and r.admin1.kind == PlaceKind.ADMIN1
    assert r.sources["country"] == "world/countries:polygon"
    assert r.sources["admin1"] == "world/admin1:polygon"
    assert r.water is None and r.disputed is None
    assert r.data_version == "world-2026.11"


def test_packs_accept_opened_pack_objects(world):
    r = Geocoder(packs=[open_pack(world)]).lookup(0.25, -139.5)
    assert r.country.id == "iso:XA" and r.admin1.id == "iso:XA-S"


def test_offshore_within_territorial_waters_keeps_the_country(geo):
    r = geo.lookup(1.1, -139.5)  # 11 km north of Alphaland's coast
    assert r.country.id == "iso:XA"
    assert r.sources["country"] == "world/countries:offshore"
    assert r.admin1.id == "iso:XA-N"
    assert r.sources["admin1"] == "world/admin1:offshore"
    assert r.water is None
    assert r.city is None  # Alpha City is 39 km away, beyond CITY_RADIUS_KM
    assert r.label == "North Province, Alphaland"


def test_far_offshore_has_no_country_but_names_the_nearest(geo):
    r = geo.lookup(1.4, -139.5)  # 44 km north of Alphaland, 67 km south of Gammaland
    assert r.country is None and r.admin1 is None and r.city is None and r.tz is None
    assert r.water.relation == Relation.OFFSHORE
    assert r.water.place.id == "iso:XA"
    assert r.water.distance_km == pytest.approx(44.5, abs=0.1)
    assert r.water.compass == "S"
    assert r.label == "Offshore, 72 km N of Alpha City"


def test_water_distance_and_bearing_are_exact(geo, world):
    """To the nearest point of the country's boundary itself, not to a sample of it."""
    countries = open_pack(world)["countries"]
    r = geo.lookup(1.4, -139.3)
    assert r.water.distance_km == pytest.approx(countries.nearest_edge_km(1.4, -139.3, 0), rel=1e-9)
    assert r.water.bearing_deg == pytest.approx(180.0, abs=0.01)  # straight down to the coast


def test_engine_uses_only_public_pack_apis():
    """The engine reads packs through placewise.packs' public API, never its private modules or
    the files inside a pack."""
    from pathlib import Path

    import placewise.engine

    for path in Path(placewise.engine.__file__).parent.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "placewise.packs._" not in source and "from placewise.packs import _" not in source, path.name
        assert '"geom"' not in source and ".npy" not in source, path.name


def test_results_carry_no_worldview_fields(geo):
    """The applied view is in Disputed where it matters, not on every answer."""
    d = geo.lookup(0.75, -139.45).to_dict()
    assert "worldview" not in d and "worldview_locked" not in d


def test_far_offshore_beyond_any_reference(geo):
    r = geo.lookup(-10.0, -160.0)
    assert r.country is None and r.water is None and r.label == "Offshore"


# --- city -------------------------------------------------------------------------------------


def test_big_far_city_beats_tiny_near_one_only_when_the_score_says_so(geo):
    alpha, tiny = (0.75, -139.5), (0.75, -139.35)
    at_tiny = (0.75, -139.35)
    between = (0.75, -139.40)
    winners = set()
    for point in (at_tiny, between):
        s_big = score(1_000_000, haversine(*point, *alpha))
        s_tiny = score(1_000, haversine(*point, *tiny))
        expected = "Alpha City" if s_big > s_tiny else "Tinyville"
        assert geo.lookup(*point).city.name == expected
        winners.add(expected)
    assert winners == {"Alpha City", "Tinyville"}, "the geometry must exercise both outcomes"


def test_city_never_crosses_a_border(geo):
    r = geo.lookup(0.25, -139.02)  # Beta Town (500k) is 5.6 km away, across the border
    assert r.country.id == "iso:XA"
    assert r.city.name == "Southby"
    assert r.city.kind == PlaceKind.LOCALITY
    assert r.tz == "Pacific/Alpha"  # the nearest city in the same country, not Beta Town's
    # near is about proximity, so it may cross the border
    names = [n.place.name for n in r.near]
    assert "Beta Town" in names
    beta = r.near[names.index("Beta Town")]
    assert beta.relation == Relation.NEAR and beta.compass == "E"
    assert beta.distance_km == pytest.approx(haversine(0.25, -139.02, 0.25, -138.97), rel=1e-6)


def test_city_prefers_the_same_admin1(geo):
    r = geo.lookup(0.495, -139.8)  # South Province; Northam is nearer but in North Province
    assert r.admin1.id == "iso:XA-S"
    assert r.city.name == "Southam"


def test_city_sections_are_not_cities(geo):
    r = geo.lookup(0.77, -139.5)  # on top of Alpha Docks (PPLX)
    assert r.city.name == "Alpha City"


def test_city_place_has_id_codes_and_point(geo):
    r = geo.lookup(0.75, -139.45)
    assert r.city.id == "geonames:1"
    assert r.city.codes["country"] == "XA"
    assert (r.city.point.lat, r.city.point.lon) == pytest.approx((0.75, -139.5))
    assert r.locality == r.city
    assert r.sources["city"] == "world/cities:score"
    assert r.tz == "Pacific/Alpha" and r.sources["tz"] == "world/cities:nearest"
    assert r.label == "Alpha City, North Province, Alphaland"


def test_no_city_in_range(geo):
    r = geo.lookup(2.4, -139.6)  # Gammaland, 24 km from Gamma Port
    assert r.city.name == "Gamma Port"
    r = geo.lookup(0.05, -138.55)  # Betaland's south-west, nothing within the radius
    assert r.city is None
    assert r.label == "West Region, Betaland"


# --- airport and near -------------------------------------------------------------------------


def test_airport_at_near_and_out_of_range(geo):
    at = geo.lookup(0.709, -139.60)  # 1 km north of Alpha International
    assert at.airport.relation == Relation.AT
    assert at.airport.place.id == "ourairports:XAAA" and at.airport.place.kind == PlaceKind.AIRPORT
    assert at.airport.place.codes == {"iata": "XAI", "icao": "XAAA", "country": "XA", "region": "XA-N"}
    assert at.airport.distance_km == pytest.approx(1.0, abs=0.01)
    near = geo.lookup(0.745, -139.60)
    assert near.airport.relation == Relation.NEAR
    assert near.airport.compass == "S" and near.airport.bearing_deg == pytest.approx(180, abs=0.5)
    assert geo.lookup(0.25, -139.02).airport is None


def test_near_lists_notable_cities_not_the_chosen_one(geo):
    r = geo.lookup(0.75, -139.45)
    assert r.city.name == "Alpha City"
    assert all(n.place.id != r.city.id for n in r.near)
    assert all(n.relation == Relation.NEAR for n in r.near)
    assert [n.distance_km for n in r.near] == sorted(n.distance_km for n in r.near)
    assert geo.lookup(0.75, -139.45, near=False).near == ()


def test_max_near_from_settings(world):
    settings = Settings(near=dataclasses.replace(Settings().near, max_near=0))
    assert Geocoder(packs=[world], settings=settings).lookup(0.25, -139.02).near == ()


# --- worldview --------------------------------------------------------------------------------


def test_disputed_filled_with_the_de_facto_view(geo):
    r = geo.lookup(2.25, -139.75)
    assert r.country.id == "iso:XC"
    d = r.disputed
    assert d.name == "Gammaland"
    assert d.claimants == ("XA", "XC")
    assert d.administered_by == "XC"
    assert d.applied_view == "de_facto" and d.locked is False


def test_worldview_column_switches_the_country(geo):
    r = geo.lookup(2.25, -139.75, worldview=("XA", "de_facto"))
    assert r.country.id == "iso:XA"
    assert r.admin1.id == "iso:XC-01"  # the data's admin1 for that ground
    assert r.disputed.applied_view == "XA" and r.disputed.administered_by == "XC"
    assert geo.lookup(2.25, -139.75, worldview=("xb",)).country.id == "iso:XC"
    assert geo.lookup(2.25, -139.75, worldview="xa").country.id == "iso:XA"
    assert geo.lookup(2.25, -139.75, worldview=("XAA",)).country.id == "iso:XA"  # ISO alpha-3 works too


def test_views_without_an_answer_fall_through(geo):
    with pytest.warns(UserWarning, match="'ZZ' is not in this pack"):
        r = geo.lookup(2.25, -139.75, worldview=("UN", "ZZ", "de_facto"))  # UN is all -99; no ZZ column
    assert r.country.id == "iso:XC" and r.disputed.applied_view == "de_facto"


def test_undisputed_ground_is_the_same_in_every_view(geo):
    r = geo.lookup(0.75, -139.45, worldview=("XB",))
    assert r.country.id == "iso:XA" and r.disputed is None


def test_lock_overrides_the_per_call_worldview(world):
    settings = Settings(worldview=WorldviewSettings(order=("XA", "de_facto"), lock=True))
    geo = Geocoder(packs=[world], settings=settings)
    r = geo.lookup(2.25, -139.75, worldview=("de_facto",))
    assert r.country.id == "iso:XA"
    assert r.disputed.locked is True and r.disputed.applied_view == "XA"


def test_lock_with_reject_refuses_another_order(world):
    settings = Settings(worldview=WorldviewSettings(order=("XA",), lock=True, conflict="reject"))
    geo = Geocoder(packs=[world], settings=settings)
    with pytest.raises(ValueError, match="worldview"):
        geo.lookup(2.25, -139.75, worldview=("XB",))
    assert geo.lookup(2.25, -139.75).country.id == "iso:XA"


def test_settings_order_applies_without_lock(world):
    settings = Settings(worldview=WorldviewSettings(order=("XA", "de_facto")))
    geo = Geocoder(packs=[world], settings=settings)
    assert geo.lookup(2.25, -139.75).country.id == "iso:XA"
    r = geo.lookup(2.25, -139.75, worldview=("de_facto",))
    assert r.country.id == "iso:XC" and r.disputed.locked is False


def test_admin1_code_of_another_country_fills_disputed(geo):
    # like Crimea in Natural Earth: the admin1 polygon is coded iso:XA-Z, inside Betaland's polygon
    r = geo.lookup(0.5, -138.25)
    assert r.country.id == "iso:XB" and r.admin1.id == "iso:XA-Z"
    assert r.disputed.name == "Zed Peninsula"
    assert r.disputed.claimants == ("XA", "XB")
    assert r.disputed.administered_by == "XB"


def test_admin1_mismatch_offshore_still_finds_its_city(geo):
    r = geo.lookup(0.5, -137.9)  # 16.7 km off Zed Peninsula; Zed Harbour is listed under XA
    assert r.country.id == "iso:XB" and r.sources["country"] == "world/countries:offshore"
    assert r.admin1.id == "iso:XA-Z"
    assert r.city.name == "Zed Harbour"
    assert r.disputed.claimants == ("XA", "XB")


# --- hooks, batch, inputs ---------------------------------------------------------------------


def test_overrides_hook_is_called_last(world):
    seen = []

    class Hook:
        def apply(self, result, lat, lon):
            seen.append((result.label, lat, lon))
            return dataclasses.replace(result, label="Overridden")

    geo = Geocoder(packs=[world], overrides=Hook())
    assert geo.lookup(0.75, -139.45).label == "Overridden"
    assert seen == [("Alpha City, North Province, Alphaland", 0.75, -139.45)]
    assert [r.label for r in geo.lookup_many([0.75, 1.4], [-139.45, -139.5])] == ["Overridden"] * 2


POINTS = [
    (0.75, -139.45), (1.1, -139.5), (1.4, -139.5), (-10.0, -160.0), (0.75, -139.35), (0.75, -139.40),
    (0.25, -139.02), (0.495, -139.8), (0.709, -139.6), (0.745, -139.6), (2.25, -139.75), (0.5, -138.25),
    (0.5, -137.9), (0.05, -138.55), (0.77, -139.5),
]  # fmt: skip


@pytest.mark.parametrize("worldview", [None, ("XA", "de_facto")])
def test_lookup_many_equals_lookup(geo, worldview):
    lat, lon = np.meshgrid(np.arange(-0.35, 2.8, 0.1), np.arange(-140.35, -137.6, 0.1), indexing="ij")
    lats = np.concatenate([lat.ravel(), [p[0] for p in POINTS]])
    lons = np.concatenate([lon.ravel(), [p[1] for p in POINTS]])
    many = geo.lookup_many(lats, lons, worldview=worldview)
    assert len(many) == len(lats)
    for r, a, b in zip(many, lats, lons, strict=True):
        assert r.to_dict() == geo.lookup(float(a), float(b), worldview=worldview).to_dict()


def test_lookup_many_empty_and_scalar_types(geo):
    assert geo.lookup_many([], []) == []
    (r,) = geo.lookup_many(np.array([0.75]), np.array([-139.45]))
    assert isinstance(r.lat, float) and r.lat == 0.75


def test_invalid_coordinates_raise(geo):
    with pytest.raises(ValueError):
        geo.lookup(91.0, 0.0)
    with pytest.raises(ValueError):
        geo.lookup_many([0.0, float("nan")], [0.0, 0.0])
    with pytest.raises(ValueError):
        geo.lookup_many([0.0, 1.0], [0.0])


def test_label_template(world):
    from placewise.model import LabelSettings

    settings = Settings(label=LabelSettings(template="{city} ({country})"))
    comma = Geocoder(packs=[world], settings=Settings(label=LabelSettings(template="{city}, {country}")))
    geo = Geocoder(packs=[world], settings=settings)
    assert geo.lookup(0.75, -139.45).label == "Alpha City (Alphaland)"
    assert comma.lookup(0.05, -138.55).label == "Betaland"  # empty parts and their separators drop


def test_default_geocoder_uses_the_store(world, monkeypatch):
    calls = []

    class FakeStore:
        def ensure(self, name):
            calls.append(name)
            return world

    geo = Geocoder(store=FakeStore())
    assert calls == ["world"]
    assert geo.lookup(0.75, -139.45).country.id == "iso:XA"


def test_module_level_lookup_uses_a_lazy_default(world, monkeypatch):
    import placewise.engine as lookup_pkg

    monkeypatch.setattr(lookup_pkg, "_default", None)
    monkeypatch.setattr(lookup_pkg, "_make_default", lambda: Geocoder(packs=[world]))
    assert lookup_pkg.lookup(0.75, -139.45).city.name == "Alpha City"
    first = lookup_pkg._default
    lookup_pkg.lookup(0.25, -139.5)
    assert lookup_pkg._default is first


# --- the real override engine -----------------------------------------------------------------


def _engine(document):
    from placewise.model import Layer
    from placewise.overrides import OverrideEngine

    return OverrideEngine.from_documents([(Layer.APP, document, "test")])


def test_override_rename_recomposes_the_label(world):
    geo = Geocoder(
        packs=[world], overrides=_engine({"rename": [{"id": "geonames:1", "name": "Alpha Metro"}]})
    )
    r = geo.lookup(0.75, -139.45)
    assert r.city.name == "Alpha Metro" and r.city.id == "geonames:1"
    assert r.label == "Alpha Metro, North Province, Alphaland"


def test_kind_tuning_widens_the_airport_search(world, geo):
    point = (0.85, -139.6)  # 16.7 km north of Alpha International, beyond NearSettings.airport
    assert geo.lookup(*point).airport is None
    tuned = Geocoder(packs=[world], overrides=_engine({"tune": [{"kind": "airport", "near_km": 20}]}))
    r = tuned.lookup(*point)
    assert r.airport.place.id == "ourairports:XAAA" and r.airport.relation == Relation.NEAR
