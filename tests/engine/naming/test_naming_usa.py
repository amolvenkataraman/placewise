"""US naming over the synthetic us pack (naming_kit): places, counties, ZCTAs and their postal
cities, principal cities."""

import pytest

from placewise.engine import Geocoder
from placewise.model import PlaceKind


def test_incorporated_place_is_locality_and_city(geo):
    """Emeryville: its own city, though Oakland (GeoNames) is bigger and close."""
    r = geo.lookup(10.52, -149.28)
    assert r.locality.id == "census:0622594" and r.locality.name == "Emeryville"
    assert r.city is r.locality and r.locality.kind == PlaceKind.LOCALITY
    assert r.sources["locality"] == r.sources["city"] == "us/places:polygon"
    assert r.label == "Emeryville, California, United States"


def test_cdp_in_a_metro_takes_its_zip_codes_postal_city(geo):
    """Paradise CDP (the Strip), ZIP Code 89109: its addresses say Las Vegas, an incorporated city."""
    r = geo.lookup(10.27, -149.85)
    assert r.locality.name == "Las Vegas" and r.city.name == "Las Vegas"
    assert r.locality.id == "census:3240000"
    assert r.sources["locality"] == r.sources["city"] == "us/places:postal"
    assert r.sublocality.name == "Paradise" and r.sublocality.id == "census:3254600"
    assert r.sublocality.kind == PlaceKind.SUBLOCALITY
    assert r.label == "Las Vegas, Nevada, United States"


def test_cdp_without_a_postal_city_stays_itself(geo):
    r = geo.lookup(10.2, -149.85)  # Paradise, in no ZCTA
    assert (r.locality.name, r.city.name) == ("Paradise", "Paradise")
    assert r.sources["locality"] == "us/places:polygon"


def test_a_postal_city_too_far_away_is_not_used(geo):
    r = geo.lookup(10.05, -149.43)  # Laughlin, whose ZIP Code names Las Vegas, 35 km off
    assert r.locality.name == "Laughlin" and r.city.name == "Laughlin"
    assert r.sources["locality"] == "us/places:polygon"


def test_cdp_named_after_its_postal_city_keeps_its_name_under_that_city(geo):
    """Like East Los Angeles (ZIP Code city Los Angeles): the name already says where it is."""
    r = geo.lookup(10.4, -149.75)
    assert (r.locality.name, r.city.name) == ("East Las Vegas", "Las Vegas")
    assert r.sources["locality"] == "us/places:polygon" and r.sources["city"] == "us/places:postal"
    assert r.label == "East Las Vegas, Nevada, United States"


def test_a_postal_city_that_is_a_cdp_names_only_small_cdps(geo):
    big = geo.lookup(10.15, -149.75)  # Winchester, 36,000 people; ZIP Code city Paradise (a CDP)
    assert (big.locality.name, big.city.name) == ("Winchester", "Winchester")
    small = geo.lookup(10.05, -149.75)  # Blue Diamond, 290 people
    assert (small.locality.name, small.city.name) == ("Paradise", "Paradise")
    assert small.sources["locality"] == "us/places:postal"
    assert small.sublocality.name == "Blue Diamond"


def test_unincorporated_land_in_a_metro_takes_its_postal_city(geo):
    """Like SFO: unincorporated San Mateo County, addressed San Francisco 94128."""
    r = geo.lookup(10.55, -149.15)
    assert r.locality.name == "San Francisco" and r.city.name == "San Francisco"
    assert r.sources["locality"] == "us/places:postal"
    assert r.postal.name == "94128"


def test_unincorporated_land_without_a_postal_city_has_a_metro_city(geo):
    """No ZCTA: no locality; the city is the metro's largest principal city in the state."""
    r = geo.lookup(10.45, -149.2)
    assert r.locality is None
    assert r.city.name == "San Francisco" and r.sources["city"] == "us/places:metro"
    assert r.admin2.name == "San Mateo County" and r.admin2.kind == PlaceKind.ADMIN2
    assert r.label == "San Francisco, California, United States"


def test_incorporated_places_ignore_the_postal_city(geo):
    r = geo.lookup(10.705, -149.8)  # New York; ZIP Code city Brooklyn
    assert r.locality.name == "New York" and r.sources["locality"] == "us/places:polygon"


def test_rural_unincorporated_land_falls_back_to_geonames(geo):
    r = geo.lookup(10.15, -149.05)  # 60 km from San Francisco
    assert r.locality is None
    assert r.city.name == "Farview" and r.sources["city"] == "world/cities:score"


def test_county_corrects_admin1(geo):
    """Natural Earth's line puts this strip in California; the county is in Nevada."""
    r = geo.lookup(10.05, -149.43)
    assert r.admin1.id == "iso:US-NV" and r.sources["admin1"] == "us/counties:state"
    assert geo.lookup(10.45, -149.2).sources["admin1"] == "us/counties:state"


def test_new_york_borough_and_sublocality(geo):
    r = geo.lookup(10.705, -149.8)
    assert r.locality.name == "New York" and r.city.name == "New York"
    assert r.borough.name == "Brooklyn" and r.borough.kind == PlaceKind.BOROUGH
    assert r.admin2.name == "Kings County"
    assert r.sublocality.name == "Williamsfield" and r.sublocality.id == "geonames:104"
    assert r.sources["borough"] == "us/counties:name"
    assert r.sources["sublocality"] == "world/cities:inside"
    assert r.label == "New York, United States"  # "New York, New York, ..." without the repeat


def test_sublocality_must_be_near_and_inside_the_locality(geo):
    assert geo.lookup(10.95, -149.6).sublocality is None  # 30 km from Williamsfield
    # Oakland's GeoNames point lies in no census place, so it isn't Emeryville's sublocality
    assert geo.lookup(10.52, -149.28).sublocality is None


def test_postal_code_and_regions(geo):
    r = geo.lookup(10.27, -149.85)
    assert r.postal.name == "89109" and r.postal.kind == PlaceKind.POSTAL_CODE
    assert r.sources["postal"] == "us/zcta:polygon"
    assert [p.id for p in r.regions] == ["census:cbsa:29820", "census:csa:332"]  # smallest first
    assert all(p.kind == PlaceKind.REGION for p in r.regions)
    assert [p.type for p in r.regions] == ["metro", "combined"]  # Place.type: no guessing from ids


def test_water_by_the_shore_takes_the_nearest_county(geo):
    r = geo.lookup(10.75, -149.495)  # 0.5 km east of Kings County, in the gap
    assert r.admin2.name == "Kings County" and r.sources["admin2"] == "us/counties:nearest"
    assert r.locality.name == "New York"
    far = geo.lookup(10.75, -149.45)  # 5 km out
    assert far.admin2 is None and far.locality is None


def test_census_city_drops_its_geonames_twin_from_near(geo, world_only):
    """GeoNames' New York City and Brooklyn lie inside the census city: not "near" it."""
    before = world_only.lookup(10.6, -149.88)
    assert before.city.name == "Brooklyn" and "New York City" in [n.place.name for n in before.near]
    r = geo.lookup(10.6, -149.88)
    assert r.city.name == "New York"
    assert not {"New York City", "Brooklyn"} & {n.place.name for n in r.near}


# --- the ZIP Code areas in their own pack (usa-zip) ------------------------------------------------

# every point the tests above look up, and a few more across the US boxes
POINTS = [
    (10.4, -149.9), (10.27, -149.85), (10.15, -149.9), (10.05, -149.75), (10.4, -149.75), (10.15, -149.75),
    (10.25, -149.9),
    (10.05, -149.42), (10.27, -149.75), (10.52, -149.27), (10.55, -149.2), (10.75, -149.2), (10.6, -149.9),
    (10.75, -149.76), (10.2, -149.05), (10.45, -149.6), (10.75, -149.495), (10.1, -149.6), (10.35, -149.3),
]  # fmt: skip


def _answers(geo, postal=True):
    out = []
    for r in geo.lookup_many([p[0] for p in POINTS], [p[1] for p in POINTS]):
        d = r.to_dict()
        d.pop("data_version")
        if not postal:
            d.pop("postal", None)
            d["sources"].pop("postal", None)
            d.get("matches", {}).pop("postal", None)
        out.append(d)
    return out


@pytest.fixture(scope="module")
def split(tmp_path_factory, packs):
    from naming_kit import write_us, write_us_zip

    root = tmp_path_factory.mktemp("zip")
    return packs[0], write_us(root, zip_pack=True), write_us_zip(root)


def test_with_usa_zip_every_answer_is_as_with_the_zip_codes_in_the_usa_pack(geo, split):
    world, us, zips = split
    with_zip = Geocoder(packs=[world, us, zips])
    got, want = _answers(with_zip), _answers(Geocoder(packs=[world, geo.packs[1]]))
    for g, w in zip(got, want, strict=True):
        w["sources"] = {k: v.replace("us/zcta", "usa-zip/zcta") for k, v in w["sources"].items()}
        if w.get("postal"):
            w["postal"]["source"] = g["postal"]["source"]
        assert g == w


def test_without_usa_zip_there_is_no_postal_code_and_the_rest_is_the_same(geo, split):
    world, us, _ = split
    without = Geocoder(packs=[world, us])
    r = without.lookup(10.27, -149.85)  # Paradise CDP, ZIP Code 89109: Las Vegas
    assert r.postal is None and "postal" not in r.sources
    assert r.locality.name == "Las Vegas" and r.sources["locality"] == "us/places:postal"
    assert _answers(without, postal=False) == _answers(Geocoder(packs=[world, geo.packs[1]]), postal=False)
