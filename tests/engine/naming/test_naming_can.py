"""Canada naming over the synthetic ca pack (naming_kit): census subdivisions and CMA roll-ups."""

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
