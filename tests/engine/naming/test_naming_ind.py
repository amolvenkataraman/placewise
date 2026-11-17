"""India naming over the synthetic in pack (naming_kit): PIN areas correct admin1 and name the
sublocality; GeoNames names the locality and city."""

from placewise.model import PlaceKind


def test_pin_area_state_corrects_admin1_and_the_city_follows(geo, world_only):
    """Like Gurugram Cyber City: Natural Earth's Delhi, the PIN area's Haryana."""
    point = (10.45, -147.8)
    before = world_only.lookup(*point)
    assert before.admin1.id == "iso:IN-DL" and before.city.name == "Kapas Hera"
    r = geo.lookup(*point)
    assert r.admin1.id == "iso:IN-HR" and r.sources["admin1"] == "in/pincodes:state"
    assert r.city.name == "Gurugram" and r.locality is r.city
    assert r.sources["city"] == "world/cities:score"
    assert r.label == "Gurugram, Haryana, India"


def test_new_iso_codes_map_to_the_world_packs_older_ones(geo):
    r = geo.lookup(10.25, -147.25)  # PIN area state IN-OD, Natural Earth's iso:IN-OR
    assert r.admin1.id == "iso:IN-OR" and r.sources["admin1"] == "in/pincodes:state"


def test_pin_code_is_the_postal_place_and_its_office_the_sublocality(geo):
    r = geo.lookup(10.8, -147.1)
    assert r.postal.name == "560066" and r.postal.id == "pin:560066"
    assert r.postal.kind == PlaceKind.POSTAL_CODE and r.sources["postal"] == "in/pincodes:polygon"
    assert r.sublocality.name == "Whitefield" and r.sublocality.id == "indiapost:560066:Whitefield S.O"
    assert r.sources["sublocality"] == "in/pincodes:name"
    assert r.city.name == "Bengaluru"
