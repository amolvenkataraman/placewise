"""World postcodes over the real world and world-postal packs: public places only. GeoNames'
codes are points, so every answer is `near`, never `within`."""

import pytest
from e2e_kit import geocoder, optional

from placewise.model import PlaceKind, Relation


@pytest.fixture(scope="module")
def geo():
    return geocoder("world", "world-postal")


# points, not areas: near a code's edge the next code's point can be nearer (the Eiffel Tower is in
# 75007 but nearest 75016's point; the Brandenburg Gate in 10117 but nearest the Bundestag's 11011)
@pytest.mark.parametrize(
    ("place", "lat", "lon", "country", "codes"),
    [
        ("Brandenburg Gate", 52.5163, 13.3777, "DE", {"10117", "11011"}),
        ("Sydney Opera House", -33.8568, 151.2153, "AU", {"2000"}),
        ("Eiffel Tower", 48.8584, 2.2945, "FR", {"75007", "75015", "75016", "75116"}),
        ("Zurich main station", 47.378, 8.540, "CH", {"8001"}),
    ],
)
def test_landmarks_get_their_postcode_near(geo, place, lat, lon, country, codes):
    r = geo.lookup(lat, lon)
    assert r.postal is not None, place
    assert r.postal.name in codes and r.postal.codes["country"] == country, place
    assert r.postal.kind == PlaceKind.POSTAL_CODE
    assert r.sources["postal"] == "world-postal/postal:nearest"
    assert r.matches["postal"].relation == Relation.NEAR and r.matches["postal"].distance_km < 5


def test_tokyo_station_gets_a_central_tokyo_code(geo):
    r = geo.lookup(35.6812, 139.7671)  # Marunouchi (100-0005); Japan's points are mostly town centres
    assert r.postal.name[:4] in {"100-", "103-", "104-"} and r.postal.codes["country"] == "JP"
    assert r.matches["postal"].relation == Relation.NEAR


def test_northern_ireland_has_no_code_from_the_uk_file(geo):
    r = geo.lookup(54.5973, -5.9301)  # Belfast City Hall
    assert r.country.name == "United Kingdom"
    assert r.postal is None or not r.postal.name.startswith("BT")


def test_countries_with_their_own_postal_areas_get_none_from_it(geo):
    for lat, lon in ((40.7580, -73.9855), (43.6426, -79.3871), (28.6315, 77.2167)):  # Times Sq, CN Tower, CP
        assert geo.lookup(lat, lon).postal is None


def test_with_the_country_packs_their_areas_still_answer():
    names = ("world", "usa", *optional("usa-zip"), "world-postal")
    r = geocoder(*names).lookup(40.7580, -73.9855)
    if "usa-zip" in names:
        assert r.postal.name == "10036" and r.matches["postal"].relation == Relation.WITHIN
    assert geocoder(*names).lookup(47.378, 8.540).postal.name == "8001"  # Zürich main station


def test_search_finds_a_code_and_its_place(geo):
    found = geo.find("75007", country="FR")
    assert found and found[0].place.name == "75007" and found[0].place.kind == PlaceKind.POSTAL_CODE
    assert found[0].country == "FR" and found[0].city == "Paris"
    assert "75007" in [e.place.name for e in geo.find("75007") if e.country == "FR"]


@pytest.mark.parametrize(("text", "code"), [("10115", "10115"), ("SW1A", "SW1A"), ("SW1A 1AA", "SW1A")])
def test_search_by_postcode(geo, text, code):
    found = geo.find(text)
    assert found and found[0].place.name == code and found[0].place.kind == PlaceKind.POSTAL_CODE
