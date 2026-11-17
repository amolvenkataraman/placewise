"""Canada naming over the synthetic ca pack (naming_kit): census subdivisions, CGNDB populated
places and CMA roll-ups."""

from placewise.model import PlaceKind


def test_subdivision_is_the_locality(geo):
    """Like Toronto Pearson: in Mississauga, though Toronto's neighbourhoods are nearer."""
    r = geo.lookup(10.48, -148.8)
    assert r.locality.name == "Mississauga" and r.locality.id == "statcan:3521005"
    assert r.city is r.locality  # 100k or more
    assert r.sources["locality"] == "ca/csd:polygon"
    assert r.admin2.name == "Peel" and r.postal.name == "L4T"
    assert r.admin1.id == "iso:CA-ON" and r.sources["admin1"] == "ca/csd:state"
    assert r.label == "Mississauga, Ontario, Canada"


def test_small_city_rolls_up_to_its_cma(geo):
    r = geo.lookup(10.25, -148.6)  # Pickering: 99k, Toronto 28x bigger
    assert r.locality.name == "Pickering" and r.city.name == "Toronto"
    assert r.city.id == "statcan:3520005" and r.sources["city"] == "ca/csd:metro"
    assert r.admin2.name == "Durham"  # from the CSDUID, though the Peel box covers it too
    assert [p.name for p in r.regions] == ["Toronto"] and r.regions[0].kind == PlaceKind.REGION


def test_city_named_in_the_cma_title_or_not_dwarfed_stays(geo):
    assert geo.lookup(10.1, -148.2).city.name == "Fort Erie"  # St. Catharines isn't 10x bigger
    assert geo.lookup(10.3, -148.4).city.name == "St. Catharines"  # in the title


def test_sublocality_from_geonames_inside_the_subdivision(geo):
    r = geo.lookup(10.89, -148.6)  # Rouge, in Toronto
    assert r.locality.name == "Toronto" and r.sublocality.name == "Rouge"
    # Eringate is 1.7 km away but in Toronto, not in Mississauga where this point is
    assert geo.lookup(10.495, -148.8).sublocality is None


def test_unorganized_subdivision_named_by_a_place_inside_it(geo):
    """Like Lake Louise in Improvement District No. 9: the GeoNames place, not the district."""
    r = geo.lookup(10.62, -148.3)
    assert r.locality.name == "Fieldbrook" and r.locality.id == "geonames:204"
    assert r.sources["locality"] == "world/cities:inside"
    assert r.city is r.locality
    empty = geo.lookup(10.72, -148.05)  # no place within RURAL_PLACE_KM
    assert empty.locality is None and empty.city is None
    assert empty.admin2.name == "Division No. 15"
    assert empty.label == "Ontario, Canada"


def test_township_named_by_its_place_else_itself(geo):
    assert geo.lookup(10.86, -148.3).locality.name == "King City"
    far = geo.lookup(10.95, -148.05)
    assert far.locality.name == "King" and far.sources["locality"] == "ca/csd:polygon"


def test_falls_by_the_river_take_the_nearest_subdivision(geo):
    r = geo.lookup(10.4, -148.015)  # 0.55 km east of Niagara Falls' clipped shore
    assert r.locality.name == "Niagara Falls" and r.sources["locality"] == "ca/csd:nearest"
    assert r.city.name == "Niagara Falls"


def test_unorganized_subdivision_named_by_a_cgndb_hamlet(geo):
    """Like Lake Louise: a hamlet GeoNames (1,000+ people) lacks names the improvement district."""
    r = geo.lookup(10.705, -148.1)
    assert r.locality.name == "Lake Lucerne" and r.locality.id == "cgndb:A1"
    assert r.locality.kind == PlaceKind.LOCALITY and r.sources["locality"] == "ca/populated_places:inside"
    assert r.city is r.locality and r.label == "Lake Lucerne, Ontario, Canada"
    assert r.admin2.name == "Division No. 15"


def test_rural_subdivision_takes_a_cgndb_settlement_before_geonames(geo):
    r = geo.lookup(10.89, -148.2)  # in King TP, 1.1 km from Kettle; King City (GeoNames) 11 km off
    assert r.locality.name == "Kettle" and r.sources["locality"] == "ca/populated_places:inside"


def test_neighbourhood_sublocality_from_cgndb(geo):
    r = geo.lookup(10.82, -148.73)  # 2.9 km from Scarbrook (whose reach is 4 km), in Toronto
    assert (r.locality.name, r.sublocality.name) == ("Toronto", "Scarbrook")
    assert r.sublocality.kind == PlaceKind.SUBLOCALITY
    assert r.sources["sublocality"] == "ca/populated_places:inside"
    small = geo.lookup(10.455, -148.9)  # 0.6 km from Maltby, an urban community (reach 1.5 km)
    assert (small.locality.name, small.sublocality.name) == ("Mississauga", "Maltby")
    assert geo.lookup(10.47, -148.9).sublocality is None  # 2.2 km from Maltby: past its reach


def test_cgndb_names_like_the_locality_are_not_its_sublocality(geo):
    assert geo.lookup(10.70, -148.601).sublocality is None  # the "Toronto" community point
