"""The design page's example points (design: "Three names per point", the EX table) over the real
world, US, Canada and India packs: what each answers now. Public places only.

Where the answer still differs from the design's target, the test says why (the data or the
rule that's missing) so a fix shows up as a test to update, not a silent change."""

import pytest
from e2e_kit import naming_geocoder


@pytest.fixture(scope="module")
def geo():
    return naming_geocoder()


def names(r):
    return {
        f: (getattr(r, f).name if getattr(r, f) is not None else None)
        for f in ("sublocality", "locality", "city", "borough", "admin1", "country")
    }


def test_fort_erie_is_in_canada_not_buffalo(geo):
    r = geo.lookup(42.905, -78.929)
    assert names(r) | {"tz": r.tz} == {
        "sublocality": "Erie Beach", "locality": "Fort Erie", "city": "Fort Erie", "borough": None,
        "admin1": "Ontario", "country": "Canada", "tz": "America/Toronto",
    }  # fmt: skip
    assert r.label == "Fort Erie, Ontario, Canada"
    # smallest first: the CMA, then the curated region (no Niagara Region polygon yet)
    assert [p.name for p in r.regions] == ["St. Catharines - Niagara", "Greater Golden Horseshoe"]
    assert r.sources["regions"] == "can/cma:polygon"


def test_las_vegas_strip_is_las_vegas(geo):
    r = geo.lookup(36.1147, -115.1728)
    assert r.label == "Las Vegas, Nevada, United States"
    assert (r.locality.name, r.city.name, r.sublocality.name) == ("Las Vegas", "Las Vegas", "Paradise")
    assert r.sources["locality"] == "usa/places:postal"  # Paradise CDP; ZIP Code 89109 says Las Vegas
    assert r.postal.name == "89109" and r.admin2.name == "Clark County"
    assert [p.id for p in r.regions] == ["region:las-vegas", "census:cbsa:29820", "census:csa:332"]


def test_emeryville_is_its_own_city(geo):
    """The design page rolls Emeryville's city up to San Francisco; incorporated US places stay
    their own city here (docs/naming.md)."""
    r = geo.lookup(37.8313, -122.2852)
    assert (r.locality.name, r.city.name) == ("Emeryville", "Emeryville")
    assert r.label == "Emeryville, California, United States"
    assert [p.name for p in r.regions] == [
        "San Francisco-Oakland-Fremont, CA Metro Area", "San Francisco Bay Area",
        "San Jose-San Francisco-Oakland, CA CSA",
    ]  # fmt: skip


def test_mission_district(geo):
    r = geo.lookup(37.7599, -122.4148)
    assert names(r)["sublocality"] == "Mission District"
    assert (r.locality.name, r.city.name) == ("San Francisco", "San Francisco")


def test_toronto_pearson_is_in_mississauga(geo):
    r = geo.lookup(43.6777, -79.6248)
    assert [p.name for p in r.regions] == [
        "Toronto", "Greater Toronto Area", "Greater Toronto and Hamilton Area", "Greater Golden Horseshoe",
    ]  # fmt: skip
    assert (r.locality.name, r.city.name) == ("Mississauga", "Mississauga")
    assert r.airport.place.codes["iata"] == "YYZ" and r.airport.relation.value == "at"
    assert r.label == "Mississauga, Ontario, Canada"


def test_markham_civic_centre(geo):
    r = geo.lookup(43.8564, -79.3374)
    assert (r.locality.name, r.city.name, r.admin2.name) == ("Markham", "Markham", "York")


def test_lake_louise_province_and_zone(geo):
    r = geo.lookup(51.4254, -116.1773)
    assert (r.admin1.name, r.country.name, r.tz) == ("Alberta", "Canada", "America/Edmonton")
    assert r.admin2.name == "Division No. 15"


def test_lake_louise_has_a_locality(geo):
    """GeoNames cities1000 has no place there; CGNDB's hamlet names Improvement District No. 9."""
    r = geo.lookup(51.4254, -116.1773)
    assert (r.locality.name, r.city.name) == ("Lake Louise", "Lake Louise")
    assert r.sources["locality"] == "can/populated_places:inside"
    assert r.label == "Lake Louise, Alberta, Canada"


def test_east_los_angeles_keeps_its_name_under_los_angeles(geo):
    r = geo.lookup(34.0232, -118.1706)  # East LA Civic Center, ZIP Code 90022 (postal city Los Angeles)
    assert (r.locality.name, r.city.name) == ("East Los Angeles", "Los Angeles")
    assert r.sources["city"] == "usa/places:postal"


def test_big_cdps_keep_their_names(geo):
    for point, name in [
        ((38.8783, -77.0687), "Arlington"),  # Arlington National Cemetery
        ((30.1617, -95.4659), "The Woodlands"),  # addressed Spring, another CDP
        ((38.9176, -77.2205), "Tysons"),  # addressed McLean, another CDP
    ]:
        r = geo.lookup(*point)
        assert (r.locality.name, r.city.name, r.sources["locality"]) == (name, name, "usa/places:polygon")


@pytest.mark.parametrize(
    ("point", "locality", "sublocality"),
    [
        ((43.7757, -79.2578), "Toronto", "Scarborough"),  # Scarborough Town Centre
        ((45.3113, -75.9088), "Ottawa", "Kanata"),  # Kanata Centrum
        ((43.7055, -79.6366), "Mississauga", "Malton"),  # Malton GO
        ((43.5555, -79.5863), "Mississauga", "Port Credit"),  # Port Credit GO
        ((49.2731, -123.1545), "Vancouver", "Kitsilano"),  # Kitsilano Beach
        ((43.6677, -79.3948), "Toronto", "Yorkville"),  # Royal Ontario Museum
    ],
)
def test_canadian_neighbourhoods_from_cgndb(geo, point, locality, sublocality):
    r = geo.lookup(*point)
    assert (r.locality.name, r.sublocality.name) == (locality, sublocality)
    assert r.sources["sublocality"] == "can/populated_places:inside"


def test_rouge_park_is_in_toronto(geo):
    r = geo.lookup(43.82, -79.17)
    assert (r.locality.name, r.city.name) == ("Toronto", "Toronto")
    assert r.sublocality.name == "Rouge"  # GeoNames' neighbourhood; the design says Scarborough


def test_gurugram_is_in_haryana(geo):
    r = geo.lookup(28.495, 77.089)
    assert (r.admin1.id, r.city.name, r.locality.name) == ("iso:IN-HR", "Gurugram", "Gurugram")
    assert r.sources["admin1"] == "ind/pincodes:state"
    assert [p.name for p in r.regions] == ["Delhi NCR (core)", "National Capital Region (India)"]
    assert r.label == "Gurugram, Haryana, India"


def test_whitefield_bengaluru(geo):
    r = geo.lookup(12.9958, 77.7608)
    assert (r.sublocality.name, r.city.name, r.admin1.name) == ("Whitefield", "Bengaluru", "Karnataka")
    assert r.postal.name == "560066"
    assert [p.name for p in r.regions] == ["Bengaluru", "Bengaluru Metropolitan Region"]


def test_horseshoe_falls_canadian_side(geo):
    r = geo.lookup(43.0799, -79.0747)
    assert (r.locality.name, r.admin1.name, r.country.name, r.tz) == (
        "Niagara Falls", "Ontario", "Canada", "America/Toronto",
    )  # fmt: skip
    assert r.sources["locality"] == "can/csd:nearest"  # the falls are off the clipped shore
    assert [p.name for p in r.regions] == ["St. Catharines - Niagara"]  # the CMA, reached from the shore


def test_williamsburg_brooklyn(geo):
    r = geo.lookup(40.7081, -73.9571)
    assert names(r) == {
        "sublocality": "Williamsburg", "locality": "New York", "city": "New York", "borough": "Brooklyn",
        "admin1": "New York", "country": "United States",
    }  # fmt: skip
    assert r.admin2.name == "Kings County" and r.postal.name == "11211"


def test_sfo_unincorporated_takes_its_postal_city(geo):
    r = geo.lookup(37.6155, -122.39)  # unincorporated San Mateo County, ZIP Code 94128
    assert (r.locality.name, r.city.name) == ("San Francisco", "San Francisco")
    assert r.sources["locality"] == "usa/places:postal" and r.postal.name == "94128"
    assert r.admin2.name == "San Mateo County"
    assert r.airport.place.codes["iata"] == "SFO" and r.airport.relation.value == "at"


def test_yosemite_valley(geo):
    r = geo.lookup(37.7456, -119.5936)
    assert (r.locality.name, r.admin1.name) == ("Yosemite Valley", "California")


def test_lookup_many_agrees_with_lookup(geo):
    points = [
        (42.905, -78.929),
        (36.1147, -115.1728),
        (43.6777, -79.6248),
        (28.495, 77.089),
        (40.7081, -73.9571),
    ]
    many = geo.lookup_many([p[0] for p in points], [p[1] for p in points])
    assert [r.to_dict() for r in many] == [geo.lookup(*p).to_dict() for p in points]
