"""packbuild.served: datasets/airports/served.json -> validation and the airports' served_city."""

import json

import pytest
from datasets_kit import needs_datasets

from packbuild import served
from placewise.packs import LayerData


def _points(name, rows, columns, coords):
    cols = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
    return LayerData(name, "point", cols, ("x",), lat=[c[0] for c in coords], lon=[c[1] for c in coords])


@pytest.fixture
def cities():
    rows = [
        ("geonames:6167865", "Toronto", "Toronto", "CA", 2_794_356),
        ("geonames:6075357", "Mississauga", "Mississauga", "CA", 668_549),
        ("geonames:5391959", "San Francisco", "San Francisco", "US", 827_526),
        ("geonames:5378538", "Oakland", "Oakland", "US", 440_646),
        ("geonames:5392171", "San Jose", "San Jose", "US", 997_368),
        ("geonames:5101798", "Newark", "Newark", "US", 281_944),
        ("geonames:5128581", "New York City", "New York City", "US", 8_804_190),
    ]
    coords = [
        (43.70, -79.42), (43.58, -79.65), (37.77, -122.42), (37.80, -122.27), (37.34, -121.89),
        (40.74, -74.17), (40.71, -74.01),
    ]  # fmt: skip
    return _points("cities", rows, ("id", "name", "asciiname", "country", "population"), coords)


@pytest.fixture
def airports():
    rows = [
        ("ourairports:CYYZ", "YYZ", "Mississauga", "CA"),
        ("ourairports:KOAK", "OAK", "Oakland", "US"),
        ("ourairports:KSJC", "SJC", "San Jose", "US"),
        ("ourairports:KEWR", "EWR", "Newark", "US"),
        ("ourairports:XNOC", "", "Nowhere", "US"),
    ]
    coords = [(43.68, -79.63), (37.72, -122.22), (37.36, -121.93), (40.69, -74.17), (10.0, 10.0)]
    return _points("airports", rows, ("id", "iata", "municipality", "country"), coords)


def _entry(iata, gid, city, country="US", **extra):
    return {"iata": iata, "city": city, "country": country, "geonames": gid, "basis": "curated", **extra}


def test_load_validates_entries(tmp_path):
    path = tmp_path / "served.json"
    good = _entry("EWR", 5128581, "New York City", notes="Newark Liberty serves New York; it lies in Newark")
    path.write_text(json.dumps({"_comment": "", "airports": [good]}), encoding="utf-8")
    assert served.load(path) == [good]
    for bad, message in [
        ({**good, "iata": "ewr1"}, "iata"),
        ({**good, "basis": "guess"}, "basis"),
        ({**good, "colour": "red"}, "unknown"),
        ({**good, "geonames": "5128581"}, "geonames"),
    ]:
        path.write_text(json.dumps({"airports": [bad]}), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            served.load(path)
    path.write_text(json.dumps({"airports": [good, good]}), encoding="utf-8")
    with pytest.raises(ValueError, match="twice"):
        served.load(path)


def test_nearby_prefers_the_big_city_over_the_airport_town(cities, airports):
    index = served.CityIndex(cities)
    lat, lon = list(airports.lat), list(airports.lon)
    # YYZ sits in Mississauga, a quarter of Toronto's size: it serves Toronto
    assert index.nearby(lat[0], lon[0], "CA") == 0
    # OAK sits in Oakland: closer than San Francisco and much closer than the bigger San Jose
    assert index.nearby(lat[1], lon[1], "US") == 3
    assert index.nearby(lat[2], lon[2], "US") == 4  # SJC: San Jose
    assert index.nearby(lat[3], lon[3], "US") == 6  # EWR: New York City, not Newark
    assert index.nearby(lat[4], lon[4], "US") is None  # nothing within reach


def test_check_finds_wrong_ids_countries_and_distances(cities, airports):
    served.check(
        [_entry("EWR", 5128581, "New York City"), _entry("SJC", 5392171, "San Jose")], cities, airports
    )
    for entry, message in [
        (_entry("EWR", 1, "Atlantis"), "no city geonames:1"),
        (_entry("EWR", 5128581, "Manhattan"), "Manhattan"),
        (_entry("YYZ", 6167865, "Toronto", country="US"), "country"),
        (_entry("YYZ", 5128581, "New York City"), "km"),  # far, and in another country
        (_entry("ZZZ", 5128581, "New York City"), "ZZZ"),  # not an airport of the layer
    ]:
        with pytest.raises(ValueError, match=message):
            served.check([entry], cities, airports)
    far = _entry("SJC", 5391959, "San Francisco", notes="test: allowed")
    served.check([far], cities, airports)  # 65 km is within MAX_KM


def test_add_sets_served_city_curated_first_then_nearby(cities, airports):
    served.add(airports, cities, [_entry("EWR", 5128581, "New York City")])
    assert list(airports.columns["served_city"]) == [
        "geonames:6167865",  # YYZ -> Toronto, by the nearby rule
        "geonames:5378538",  # OAK -> Oakland
        "geonames:5392171",  # SJC -> San Jose
        "geonames:5128581",  # EWR -> New York City, curated
        "",  # no city around
    ]
    assert airports.types["served_city"] == "str" and "placewise-names" in airports.sources


@needs_datasets
def test_the_dataset_serves_the_famous_airports_right():
    found = {e["iata"]: e for e in served.load()}
    for code, city in [
        ("YYZ", "Toronto"), ("YVR", "Vancouver"), ("DEL", "Delhi"), ("BOM", "Mumbai"), ("BLR", "Bengaluru"),
        ("HYD", "Hyderabad"), ("MAA", "Chennai"), ("CCU", "Kolkata"), ("SFO", "San Francisco"),
        ("OAK", "Oakland"), ("SJC", "San Jose"), ("JFK", "New York City"), ("LGA", "New York City"),
        ("EWR", "New York City"), ("LHR", "London"), ("CDG", "Paris"), ("NRT", "Tokyo"), ("HND", "Tokyo"),
    ]:  # fmt: skip
        assert found[code]["city"] == city, code
    assert len(found) > 1500
