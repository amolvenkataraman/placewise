"""US naming over the synthetic us pack (naming_kit): places, counties, ZCTAs, metro roll-ups."""

from placewise.model import PlaceKind


def test_incorporated_place_is_locality_and_city(geo):
    """Emeryville: its own city, though Oakland (GeoNames) is bigger and close."""
    r = geo.lookup(10.52, -149.28)
    assert r.locality.id == "census:0622594" and r.locality.name == "Emeryville"
    assert r.city is r.locality and r.locality.kind == PlaceKind.LOCALITY
    assert r.sources["locality"] == r.sources["city"] == "us/places:polygon"
    assert r.label == "Emeryville, California, United States"


def test_cdp_in_a_metro_takes_the_principal_city(geo):
    """Paradise CDP (the Strip) -> Las Vegas, the CBSA title's first city in the same state."""
    r = geo.lookup(10.2, -149.85)
    assert r.locality.name == "Las Vegas" and r.city.name == "Las Vegas"
    assert r.locality.id == "census:3240000"
    assert r.sources["locality"] == r.sources["city"] == "us/places:metro"
    assert r.sublocality.name == "Paradise" and r.sublocality.id == "census:3254600"
    assert r.sublocality.kind == PlaceKind.SUBLOCALITY
    assert r.label == "Las Vegas, Nevada, United States"


def test_cdp_far_from_its_principal_city_stays_itself(geo):
    r = geo.lookup(10.05, -149.43)  # Laughlin, 60 km from Las Vegas' internal point
    assert r.locality.name == "Laughlin" and r.city.name == "Laughlin"
    assert r.sources["locality"] == "us/places:polygon"


def test_unincorporated_land_has_no_locality_but_a_metro_city(geo):
    """Like SFO: unincorporated San Mateo County, 33 km from San Francisco."""
    r = geo.lookup(10.45, -149.2)
    assert r.locality is None
    assert r.city.name == "San Francisco" and r.sources["city"] == "us/places:metro"
    assert r.admin2.name == "San Mateo County" and r.admin2.kind == PlaceKind.ADMIN2
    assert r.label == "San Francisco, California, United States"


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
    r = geo.lookup(10.2, -149.85)
    assert r.postal.name == "89109" and r.postal.kind == PlaceKind.POSTAL_CODE
    assert r.sources["postal"] == "us/zcta:polygon"
    assert [p.id for p in r.regions] == ["census:cbsa:29820", "census:csa:332"]  # smallest first
    assert all(p.kind == PlaceKind.REGION for p in r.regions)


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
