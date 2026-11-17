"""Geometry, places and answers: validation, immutability and the dict round trip that the client,
server and caches depend on."""

import dataclasses
import json

import numpy as np
import pytest

from placewise.model import (
    BBox,
    Disputed,
    Entity,
    Nearby,
    Outline,
    Place,
    PlaceKind,
    Point,
    Relation,
    Relative,
    Result,
)


def test_point_validates_and_is_immutable():
    p = Point(43.65, -79.38)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.lat = 0
    for bad in [(91, 0), (0, 181), (float("nan"), 0)]:
        with pytest.raises(ValueError):
            Point(*bad)


def test_bbox_validation_and_antimeridian():
    assert not BBox(43, -80, 44, -79).crosses_antimeridian
    box = BBox(-1, 178.5, 1, -179.5)
    assert box.crosses_antimeridian
    assert box.contains(0, 179) and box.contains(0, -179.9) and not box.contains(0, 0)
    with pytest.raises(ValueError):
        BBox(10, 0, 5, 1)  # south above north


def test_outline_contains_and_area():
    square = Outline((((0, 0), (0, 1), (1, 1), (1, 0)),))
    assert square.contains(0.5, 0.5) and not square.contains(2, 2)
    assert square.area_km2 == pytest.approx(12364, rel=1e-3)  # ~1°x1° at the equator
    with pytest.raises(ValueError):
        Outline((((0, 0), (0, 1)),))  # a ring needs at least three corners


def test_place_kind_is_coerced_and_required_fields_checked():
    park = Place("wikidata:Q180402", "Yosemite National Park", "park", tier=1)
    assert park.kind is PlaceKind.PARK
    with pytest.raises(ValueError):
        Place("", "Nameless", PlaceKind.PARK)
    with pytest.raises(ValueError):
        Place("x:1", "Bad kind", "volcano-ish")


def _example_result():
    toronto = Place("geonames:6167865", "Toronto", PlaceKind.LOCALITY, point=Point(43.70, -79.42))
    yyz = Place(
        "ourairports:CYYZ", "Toronto Pearson", PlaceKind.AIRPORT, codes={"iata": "YYZ", "icao": "CYYZ"}
    )
    return Result(
        lat=43.6777,
        lon=-79.6248,
        label="At YYZ Toronto Pearson",
        country=Place("iso:CA", "Canada", PlaceKind.COUNTRY, codes={"iso2": "CA"}),
        admin1=Place("iso:CA-ON", "Ontario", PlaceKind.ADMIN1),
        city=toronto,
        locality=Place("statcan:3521005", "Mississauga", PlaceKind.LOCALITY),
        tz="America/Toronto",
        regions=(Place("region:gta", "GTA", PlaceKind.REGION),),
        airport=Nearby(yyz, Relation.AT, 0.0, None, None),
        sources={"locality": "statcan-boundaries-2021"},
        data_version="2026.11",
        worldview=("de_facto",),
    )


def test_result_round_trips_through_plain_json():
    result = _example_result()
    as_json = json.dumps(result.to_dict())
    again = Result.from_dict(json.loads(as_json))
    assert again == result
    assert again.airport.place.codes["iata"] == "YYZ"
    assert again.cc == "CA"


def test_to_dict_is_compact_and_ordered():
    d = _example_result().to_dict()
    assert "water" not in d and "near" not in d  # None and empty values are left out
    assert list(d)[:3] == ["lat", "lon", "label"]  # field order is the declaration order
    assert d["airport"]["relation"] == "at"


def test_from_dict_rejects_unknown_fields():
    with pytest.raises(ValueError, match="colour"):
        Point.from_dict({"lat": 1, "lon": 2, "colour": "red"})


def test_disputed_relative_and_entity_shapes():
    d = Disputed(
        "Kashmir", ("IN", "PK"), administered_by="PK", applied_view="de_facto", views={"IN": "IN-LA"}
    )
    assert Disputed.from_dict(d.to_dict()) == d
    r = Relative("home", 12.1, 225.0, "SW", inside=False)
    assert r.to_dict()["compass"] == "SW"
    e = Entity(
        Place("wikidata:Q180402", "Yosemite National Park", PlaceKind.PARK),
        point=Point(37.84, -119.51),
        bbox=BBox(37.49, -119.89, 38.19, -119.20),
        radius_km=50.0,
    )
    assert Entity.from_dict(e.to_dict()) == e
    with pytest.raises(ValueError):
        Entity(e.place, point=e.point, bbox=e.bbox, radius_km=-1)


def test_feature_contains_bbox_and_round_trip():
    from placewise.model import Feature

    f = Feature(
        outlines=(Outline((((0, 0), (0, 1), (1, 1), (1, 0)),)), Outline((((5, 5), (5, 6), (6, 6), (6, 5)),))),
        properties={"name": "Two cells", "rank": 2},
        id="cells",
    )
    assert f.contains(0.5, 0.5) and f.contains(5.5, 5.5) and not f.contains(3, 3)
    assert f.bbox == BBox(0, 0, 6, 6)
    assert Feature.from_dict(f.to_dict()) == f


def test_entity_contains_uses_the_outline_or_falls_back_to_the_radius():
    park = Place("wikidata:Q180402", "Yosemite National Park", PlaceKind.PARK)
    square = Outline((((37.0, -120.0), (37.0, -119.0), (38.0, -119.0), (38.0, -120.0)),))
    with_outline = Entity(park, point=Point(37.5, -119.5), bbox=square.bbox, radius_km=80.0, outline=square)
    assert with_outline.contains(37.2, -119.2) and not with_outline.contains(38.5, -119.5)
    # no outline: a circle of radius_km around the point (1° of latitude is ~111.2 km)
    circle = Entity(park, point=Point(0.0, -20.0), bbox=BBox(-1, -21, 1, -19), radius_km=100.0)
    assert circle.contains(0.8, -20.0) and not circle.contains(1.0, -20.0)
    assert list(circle.contains(np.array([0.0, 2.0]), np.array([-20.0, -20.0]))) == [True, False]
