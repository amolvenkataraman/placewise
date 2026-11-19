"""Precise borders and islands on the real packs (placewise.engine._borders): the country packs'
states and provinces decide the country where Natural Earth's 1:10m outlines are off. Public
places only; each pair is a point on either side of the border, a kilometre or more from it.

Skipped when a pack isn't built.
"""

import pytest
from e2e_kit import geocoder

from placewise.model import Relation

PACKS = ("world", "usa", "can", "ind", "world-water")

SIDES = [
    # name, (lat, lon), country, admin1
    ("Niagara Falls, NY (downtown)", (43.0875, -79.0620), "United States", "New York"),
    ("Niagara Falls, NY (Pine Avenue)", (43.0985, -79.0590), "United States", "New York"),
    ("Goat Island, NY", (43.0812, -79.0640), "United States", "New York"),
    ("Niagara Falls, ON (Clifton Hill)", (43.0910, -79.0750), "Canada", "Ontario"),
    ("Detroit, Renaissance Center", (42.3293, -83.0398), "United States", "Michigan"),
    ("Windsor, ON (downtown)", (42.3149, -83.0364), "Canada", "Ontario"),
    ("Sault Ste. Marie, MI", (46.4950, -84.3453), "United States", "Michigan"),
    ("Sault Ste. Marie, ON", (46.5136, -84.3358), "Canada", "Ontario"),
    ("Point Roberts, WA", (48.9850, -123.0600), "United States", "Washington"),
    ("Tsawwassen, BC", (49.0110, -123.0830), "Canada", "British Columbia"),
    ("Blaine, WA", (48.9930, -122.7470), "United States", "Washington"),
    ("White Rock, BC", (49.0250, -122.8030), "Canada", "British Columbia"),
    ("Derby Line, VT", (45.0030, -72.0980), "United States", "Vermont"),
    ("Stanstead, QC", (45.0090, -72.0970), "Canada", "Québec"),
    ("Cornwall, ON", (45.0213, -74.7300), "Canada", "Ontario"),
    ("Massena, NY", (44.9281, -74.8919), "United States", "New York"),
    ("Raxaul, Bihar", (26.9800, 84.8500), "India", "Bihar"),
    ("Birgunj", (27.0104, 84.8770), "Nepal", None),
    ("Bangaon, West Bengal", (23.0450, 88.8200), "India", "West Bengal"),
    ("Benapole", (23.0420, 88.9050), "Bangladesh", None),
]


@pytest.fixture(scope="module")
def geo():
    return geocoder(*PACKS)


@pytest.mark.parametrize(("name", "point", "country", "admin1"), SIDES, ids=[s[0] for s in SIDES])
def test_each_side_of_the_border(geo, name, point, country, admin1):
    r = geo.lookup(*point)
    assert r.country is not None and r.country.name == country, name
    if admin1 is not None:
        assert r.admin1.name == admin1, name
    assert r.matches["country"].relation is Relation.WITHIN and r.disputed is None


def test_niagara_falls_ny_is_named_in_the_us(geo):
    r = geo.lookup(43.0875, -79.0620)
    assert r.sources["country"] == "usa/states:polygon" and r.city.name == "Niagara Falls"
    assert r.label == "Niagara Falls, New York, United States"
    assert r.certain


ISLANDS = [
    # name, (lat, lon), country, admin1
    ("Treasure Island, San Francisco", (37.8235, -122.3706), "United States", "California"),
    ("Yerba Buena Island", (37.8100, -122.3640), "United States", "California"),
    ("Alcatraz Island", (37.8267, -122.4230), "United States", "California"),
    ("Angel Island", (37.8609, -122.4326), "United States", "California"),
    ("Centre Island, Toronto", (43.6205, -79.3790), "Canada", "Ontario"),
    ("Wolfe Island, Ontario", (44.1900, -76.4300), "Canada", "Ontario"),
    ("Mackinac Island, Michigan", (45.8492, -84.6189), "United States", "Michigan"),
]


@pytest.mark.parametrize(("name", "point", "country", "admin1"), ISLANDS, ids=[s[0] for s in ISLANDS])
def test_islands_are_land(geo, name, point, country, admin1):
    r = geo.lookup(*point)
    assert r.country.name == country and r.admin1.name == admin1, name
    assert r.water is None or r.water.relation not in (Relation.ON, Relation.OVER), name
    assert not r.label.startswith(("On ", "Over ", "Offshore")), r.label
    assert r.matches["country"].relation is Relation.WITHIN


def test_treasure_island_has_the_bay_near(geo):
    r = geo.lookup(37.8235, -122.3706)
    assert r.city.name == "San Francisco" and r.sources["country"] == "usa/states:polygon"
    assert "San Francisco Bay" in {n.place.name for n in r.near}


WATER = [
    ("San Francisco Bay, off Hunters Point", (37.7300, -122.3300), "On San Francisco Bay"),
    ("Lake Ontario, mid-lake", (43.6000, -77.9000), "On Lake Ontario"),
    ("Lake Ontario, off the Toronto Islands", (43.5800, -79.3800), "On Lake Ontario"),
    ("Straits of Mackinac", (45.8150, -84.7600), None),
]


@pytest.mark.parametrize(("name", "point", "label"), WATER, ids=[w[0] for w in WATER])
def test_open_water_stays_water(geo, name, point, label):
    r = geo.lookup(*point)
    assert r.water is not None and r.water.relation is Relation.ON, name
    if label is not None:
        assert r.label == label
