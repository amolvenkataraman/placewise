"""Precise borders (placewise.engine._borders): a country pack's states or provinces decide the
country where Natural Earth's coarse polygons put a point in the wrong country, or in none.

naming_kit's world: "US" lon -150 .. -149, "CA" -149 .. -148, "IN" -148 .. -147 (lat 10 .. 11).
Here the us pack's "California" reaches 0.02° (~2 km) past Natural Earth's border into "Canada"
(like Niagara Falls, NY), Canada's Ontario starts 0.01° east of that, so the two overlap by
nothing; and an island off New York's north shore is on no Natural Earth polygon."""

import numpy as np
import pytest

from placewise.engine import Geocoder, _borders
from placewise.model import Feature, Relation
from placewise.packs import LayerData, write_pack
from tests.engine.naming.naming_kit import box, polygons, write_ca, write_in, write_us, write_world

EAST = -148.98  # the us pack's California ends here (Natural Earth's border is at -149)
ISLAND = (11.03, -149.85)  # north of every Natural Earth polygon, inside a New York unit
US_STATES = [
    # boxes, id, name, usps
    ([(10.5, -150, 11, -149.5), (11.02, -149.9, 11.04, -149.8)], "iso:US-NY", "New York", "NY"),  # + island
    ([(10, -150, 10.5, -149.5)], "iso:US-NV", "Nevada", "NV"),
    ([(10, -149.5, 11, EAST)], "iso:US-CA", "California", "CA"),
    ([(12, -150, 12.5, -149.5)], "iso:US-GU", "Guam", "GU"),  # a territory the world pack doesn't know
]


def _states(rows=US_STATES):
    features = [Feature(tuple(box(*b).outlines[0] for b in r[0])) for r in rows]
    columns = {"id": [r[1] for r in rows], "name": [r[2] for r in rows], "usps": [r[3] for r in rows]}
    return LayerData("states", "polygon", columns, ("uscensus",), features=features)


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    out = tmp_path_factory.mktemp("borders")
    world = write_world(out)
    us = write_us(out, extra=(_states(),))
    ca = write_ca(out, provinces=[((10, EAST + 0.01, 11, -148), "statcan:35", "Ontario", "ON")])
    return world, us, ca, write_in(out)


@pytest.fixture(scope="module")
def geo(packs):
    return Geocoder(packs=list(packs))


def test_a_state_reaching_past_natural_earths_border_decides_the_country(geo):
    r = geo.lookup(10.75, -148.99)  # Natural Earth: Canada; the us pack: California
    assert r.country.name == "United States" and r.admin1.name == "California"
    assert r.sources["country"] == "us/states:polygon"
    assert r.matches["country"].relation is Relation.WITHIN and r.matches["country"].distance_km == 0
    assert r.disputed is None


def test_beyond_the_state_natural_earth_stands(geo):
    # 44 m inside the unit: within its own generalisation (BORDER_DEPTH_KM), so not evidence
    assert geo.lookup(10.75, EAST - 0.0004).country.name == "Canada"
    r = geo.lookup(10.75, -148.95)
    assert r.country.name == "Canada" and r.sources["country"] == "world/countries:polygon"
    assert geo.lookup(10.75, -149.5).country.name == "United States"


def test_a_province_reaching_past_natural_earths_border_decides_too(tmp_path):
    ca = write_ca(tmp_path, provinces=[((10, -149.03, 11, -148), "statcan:35", "Ontario", "ON")])
    california = _states([([(10, -149.5, 11, -149.03)], "iso:US-CA", "California", "CA")])
    us = write_us(tmp_path, extra=(california,))
    geo = Geocoder(packs=[write_world(tmp_path), us, ca])
    r = geo.lookup(10.75, -149.01)  # Natural Earth: US; only Ontario holds it
    assert r.country.name == "Canada" and r.sources["country"] == "ca/provinces:polygon"
    assert r.admin1.name == "Ontario"


def test_where_both_packs_hold_the_point_natural_earth_decides(tmp_path):
    ca = write_ca(tmp_path, provinces=[((10, -149.05, 11, -148), "statcan:35", "Ontario", "ON")])
    us = write_us(tmp_path, extra=(_states(),))  # California to -148.98: both hold -149.02 .. -148.98
    geo = Geocoder(packs=[write_world(tmp_path), us, ca])
    assert geo.lookup(10.75, -148.99).country.name == "Canada"
    assert geo.lookup(10.75, -149.01).country.name == "United States"


def test_an_island_on_no_natural_earth_polygon_is_land(geo):
    r = geo.lookup(*ISLAND)
    assert r.country.name == "United States" and r.sources["country"] == "us/states:polygon"
    assert r.admin1.name == "New York" and not r.label.startswith("Offshore")


def test_a_territory_the_world_pack_does_not_know_is_left_out(geo):
    r = geo.lookup(12.25, -149.75)
    assert r.country is None


def test_without_the_state_layers_nothing_changes(packs, tmp_path):
    world, _, _, ind = packs
    plain = Geocoder(packs=[world, write_us(tmp_path), write_ca(tmp_path), ind])
    assert plain.lookup(10.75, -148.99).country.name == "Canada"
    world_only = Geocoder(packs=[world])
    assert not _borders.Borders(world_only.layers, world_only.admin)


def test_lookup_many_equals_lookup(geo):
    lats = np.array([10.75, 10.75, 10.75, ISLAND[0], 12.25, 10.2, 10.75])
    lons = np.array([-148.99, -148.95, -149.5, ISLAND[1], -149.75, -147.8, -148.99])
    many = geo.lookup_many(lats, lons)
    single = [geo.lookup(a, b) for a, b in zip(lats, lons, strict=True)]
    assert [r.to_dict() for r in many] == [r.to_dict() for r in single]


# -- the rule's edges, on handmade answers -------------------------------------------------------


def test_never_inside_a_disputed_area(geo):
    borders = _borders.Borders(geo.layers, geo.admin)
    rows = geo.admin.worldviews.row_of_iso2
    lat, lon = np.array([10.75, 10.75]), np.array([-148.99, -148.99])
    a = {
        "cidx": np.array([rows["CA"], rows["CA"]]), "cmode": np.array(["polygon", "polygon"], dtype=object),
        "area": np.array([3, -1]),  # the first is in a disputed area
    }  # fmt: skip
    borders.answer(a, lat, lon)
    assert a["cidx"].tolist() == [rows["CA"], rows["US"]]
    assert a["csrc"].tolist() == [None, "us/states:polygon"]


def test_units_only_one_view_gives_a_country_are_left_out(tmp_path):
    rows = [
        ((10, -148.03, 11, -147), "lgd:state:6", "Haryana", "IN-HR", ""),
        ((10, -148.06, 11, -148.03), "lgd:state:6#india-view", "Haryana", "IN-HR", "1"),
    ]
    states = polygons("states", rows, ("id", "name", "iso", "india_view_only"), "lgd")
    geo = Geocoder(packs=[write_world(tmp_path), write_in(tmp_path, extra=(states,))])
    r = geo.lookup(10.75, -148.01)
    assert r.country.name == "India" and r.sources["country"] == "in/states:polygon"
    assert geo.lookup(10.75, -148.045).country.name == "Canada"  # the flagged unit: left out


def test_india_states_correct_land_borders_only(tmp_path):
    # unions of PIN-code areas take in lagoons: no evidence of land where Natural Earth has none
    rows = [((10, -148.03, 11.05, -147), "lgd:state:6", "Haryana", "IN-HR", "")]
    states = polygons("states", rows, ("id", "name", "iso", "india_view_only"), "lgd")
    geo = Geocoder(packs=[write_world(tmp_path), write_in(tmp_path, extra=(states,))])
    r = geo.lookup(11.03, -147.5)  # north of Natural Earth's India, inside the unit
    assert r.sources["country"] == "world/countries:offshore"


def test_an_island_in_a_bay_is_land_with_the_bay_near(packs, tmp_path):
    columns = ("id", "name", "type", "wikidata", "aliases")
    marine = polygons("marine", [((11, -150, 12, -147), "ne:1", "North Bay", "bay", "", "")], columns)
    water = write_pack(tmp_path / "water", "world-water", "2026.11", [marine], created="2026-11-17T00:00:00Z")
    geo = Geocoder(packs=[*packs, water])
    r = geo.lookup(*ISLAND)
    assert r.water is None and r.country.name == "United States"
    assert {n.place.name: n.relation for n in r.near}.get("North Bay") is Relation.NEAR
    sea = geo.lookup(11.5, -149.85)  # open water: on the bay, as before
    assert sea.water.place.name == "North Bay" and sea.label.startswith(("On North Bay", "Over North Bay"))
