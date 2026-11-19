"""World postcodes in lookups (placewise.engine._nearby.postal) over lookup_kit's world and a synthetic
world-postal pack (postal_kit): the nearest code of the point's own country within its reach,
always `near` (the codes are points, not areas)."""

import numpy as np
import pytest
from lookup_kit import write_world
from postal_kit import write_postal

from placewise.constants import lookup as lookup_const
from placewise.constants import postal as const
from placewise.engine import Geocoder
from placewise.geo import haversine
from placewise.model import PlaceKind, Relation
from tests.engine.naming.naming_kit import write_us
from tests.engine.naming.naming_kit import write_world as write_naming_world


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    root = tmp_path_factory.mktemp("postal")
    return write_world(root), write_postal(root)


@pytest.fixture(scope="module")
def geo(packs):
    return Geocoder(packs=list(packs))


def test_the_nearest_code_of_the_country_answers_near_with_the_distance(geo):
    r = geo.lookup(0.76, -139.5)
    assert r.postal.name == "A100" and r.postal.kind == PlaceKind.POSTAL_CODE
    assert r.postal.id == "postal:XA:A100"
    assert r.postal.codes == {"place": "Alpha City", "country": "XA"}
    assert r.sources["postal"] == "world-postal/postal:nearest"
    km = float(haversine(0.76, -139.5, 0.75, -139.5))
    assert r.matches["postal"].relation == Relation.NEAR
    assert r.matches["postal"].distance_km == pytest.approx(km, abs=1e-3)
    assert r.label == geo.lookup(0.76, -139.5).label  # the label is not about postcodes


def test_a_codes_other_point_answers_where_it_is_nearer(geo):
    r = geo.lookup(0.75, -139.32)
    assert r.postal.name == "A100" and r.postal.id == "postal:XA:A100:2"
    assert r.postal.codes["place"] == "East Alpha"
    assert r.matches["postal"].distance_km == pytest.approx(2.2, abs=0.1)


def test_beyond_the_reach_there_is_no_code(geo):
    r = geo.lookup(0.5, -139.75)  # 39 km from A100, reach 10 km
    assert r.postal is None and "postal" not in r.sources and "postal" not in r.matches


def test_another_countrys_code_never_answers(geo):
    r = geo.lookup(0.5, -139.02)  # in Alphaland, 4.4 km from Betaland's B-1
    assert r.country.name == "Alphaland" and r.postal is None
    assert geo.lookup(0.5, -138.9).postal.name == "B-1"


def test_a_country_with_one_code_has_it_everywhere(geo):
    r = geo.lookup(2.45, -139.55)  # 31 km from GC1's point, past its reach
    assert r.postal.name == "GC1" and r.matches["postal"].relation == Relation.NEAR
    assert r.matches["postal"].distance_km == pytest.approx(31.4, abs=0.5)


def test_the_worldviews_country_decides_whose_codes_apply(geo):
    assert geo.lookup(2.25, -139.75).postal.name == "GC1"
    r = geo.lookup(2.25, -139.75, worldview="XA")  # Alphaland's view: the island is Alphaland
    assert r.country.name == "Alphaland" and r.postal is None


def test_far_offshore_there_is_no_code(geo):
    assert geo.lookup(-10.0, -160.0).postal is None


def test_lookup_many_equals_lookup(geo):
    lat = np.array([0.76, 0.75, 0.5, 2.45, -10.0])
    lon = np.array([-139.5, -139.32, -139.75, -139.55, -160.0])
    assert geo.lookup_many(lat, lon) == [geo.lookup(a, b) for a, b in zip(lat, lon, strict=True)]


def test_search_context_lookups_have_the_code_too(geo):
    assert geo._lookup_places([0.76], [-139.5])[0].postal.name == "A100"


def test_without_the_pack_lookups_are_unchanged(packs, geo):
    land = Geocoder(packs=[packs[0]])
    r, with_postal = land.lookup(0.76, -139.5), geo.lookup(0.76, -139.5)
    assert r.postal is None
    assert r.label == with_postal.label and r.city == with_postal.city and r.near == with_postal.near


def test_a_country_packs_postal_area_wins(tmp_path):
    # a stray point of the country's own in the postcode pack never replaces the ZIP Code area
    rows = [("postal:US:99999", "99999", "Nowhere", "US", 10.25, -149.9, 30.0, False)]
    geo = Geocoder(packs=[write_naming_world(tmp_path), write_us(tmp_path), write_postal(tmp_path, rows)])
    r = geo.lookup(10.25, -149.9)
    assert r.postal.name == "89109" and r.sources["postal"] == "us/zcta:polygon"


def test_the_default_geocoder_opens_an_installed_postal_pack():
    assert const.PACK in lookup_const.OPTIONAL_PACKS
