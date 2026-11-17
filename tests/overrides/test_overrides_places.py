"""placewise.overrides.places: hide and add rules."""

import dataclasses

from overrides_kit import (
    KARIYA_PARK,
    LAKE_ONTARIO,
    PEARSON,
    RATTRAY_MARSH,
    apply,
    engine,
    mississauga_result,
    toronto_result,
)


def test_hide_drops_within_near_and_airport_entries():
    eng = engine(
        app={"hide": [{"id": KARIYA_PARK.id}, {"id": RATTRAY_MARSH.id}, {"id": PEARSON.id}]},
    )
    out = apply(eng, mississauga_result())
    assert out.within == ()
    assert [n.place.id for n in out.near] == [LAKE_ONTARIO.id]
    assert out.airport is None
    assert out.sources["within"] == "override:app:app.toml#1"
    assert out.sources["near"] == "override:app:app.toml#2"
    assert out.sources["airport"] == "override:app:app.toml#3"


def test_hide_in_a_lower_layer_loses_to_an_add_in_a_higher_one():
    add = {
        "kind": "park",
        "name": "Kariya Park",
        "id": KARIYA_PARK.id,
        "point": {"lat": 43.5903, "lon": -79.6366},
    }
    eng = engine(repo={"hide": [{"id": KARIYA_PARK.id}]}, local={"add": [{**add, "radius_m": 2000}]})
    out = apply(eng, mississauga_result())
    assert [p.id for p in out.within] == [KARIYA_PARK.id]
    assert out.sources["within"] == "override:local:local.toml#1"


def test_add_matches_by_radius():
    add = {"kind": "landmark", "name": "Celebration Square", "point": {"lat": 43.5890, "lon": -79.6430}}
    eng = engine(local={"add": [{**add, "radius_m": 300}]})
    out = apply(eng, mississauga_result())
    assert out.within[0].name == "Celebration Square" and out.within[0].kind.value == "landmark"
    assert out.within[0].id == "override:local:local.toml#1"  # no id given
    assert out.within[1] == KARIYA_PARK
    assert out.sources["within"] == "override:local:local.toml#1"
    assert apply(eng, toronto_result()).within == ()


def test_add_matches_by_area_and_airports_fill_the_airport_slot():
    islands = {
        "kind": "park",
        "name": "Toronto Island Park",
        "id": "local:toronto-islands",
        "point": {"lat": 43.6205, "lon": -79.3780},
        "within": {"bbox": {"south": 43.60, "west": -79.40, "north": 43.635, "east": -79.34}},
    }
    eng = engine(local={"add": [islands]})
    on_island = dataclasses.replace(toronto_result(), lat=43.62, lon=-79.37)
    assert apply(eng, on_island).within[0].id == "local:toronto-islands"
    assert apply(eng, toronto_result()).within == ()  # City Hall is north of the box

    ytz = {
        "kind": "airport",
        "name": "Billy Bishop Toronto City Airport",
        "point": {"lat": 43.6275, "lon": -79.3962},
    }
    out = apply(
        engine(local={"add": [{**ytz, "radius_m": 1500}]}),
        dataclasses.replace(toronto_result(), lat=43.628, lon=-79.396),
    )
    assert out.airport.place.name == "Billy Bishop Toronto City Airport"
    assert out.airport.relation.value == "at" and out.airport.distance_km < 1
    assert out.sources["airport"] == "override:local:local.toml#1"
