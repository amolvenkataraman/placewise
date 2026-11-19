"""placewise.overrides.rules.labels: rename and label rules."""

import dataclasses

from overrides_kit import (
    ALAMEDA,
    LAKE_ONTARIO,
    MISSISSAUGA,
    PEEL,
    apply,
    engine,
    mississauga_result,
    oakland_result,
)


def test_rename_changes_the_place_everywhere_it_appears():
    eng = engine(repo={"rename": [{"id": MISSISSAUGA.id, "name": "Sauga", "aliases": ["The Sauga"]}]})
    out = apply(eng, mississauga_result())
    assert out.locality.name == out.city.name == "Sauga"
    assert out.locality.id == MISSISSAUGA.id  # same entity, new name
    assert "Mississauga" in out.locality.aliases and "The Sauga" in out.locality.aliases
    assert out.sources["city"] == out.sources["locality"] == "override:repo:repo.toml#1"
    assert out.label == "Mississauga, Ontario"  # labels are composed by lookup, see relabel
    lake = engine(repo={"rename": [{"id": LAKE_ONTARIO.id, "name": "Lake Ontario (Lac Ontario)"}]})
    out = apply(lake, mississauga_result())
    assert out.near[0].place.name == "Lake Ontario (Lac Ontario)" and out.sources["near"].startswith(
        "override:"
    )
    assert apply(eng, oakland_result()) == oakland_result()  # no such id: untouched


def test_label_sets_fields_inside_its_area_only():
    rule = {
        "within": {"point": {"lat": 43.5503, "lon": -79.5868}, "km": 1.0},
        "fields": {"sublocality": "Port Credit", "label": "Port Credit, Mississauga"},
    }
    eng = engine(repo={"label": [rule]})
    port_credit = dataclasses.replace(mississauga_result(), lat=43.5503, lon=-79.5868)
    out = eng.apply(port_credit, 43.5503, -79.5868, relabel=lambda r: "should not be used")
    assert out.sublocality.name == "Port Credit" and out.sublocality.kind.value == "sublocality"
    assert out.label == "Port Credit, Mississauga"
    assert out.sources["label"] == out.sources["sublocality"] == "override:repo:repo.toml#1"
    assert apply(eng, mississauga_result()) == mississauga_result()  # 5 km away: outside


def test_label_renames_an_existing_field_in_place():
    eng = engine(repo={"label": [{"within": {"country": "US"}, "fields": {"admin2": "Alameda"}}]})
    out = apply(eng, oakland_result())
    assert out.admin2.name == "Alameda" and out.admin2.id == ALAMEDA.id


def test_label_region_field_puts_a_region_first():
    rule = {"within": {"place": PEEL.id}, "fields": {"region": "Greater Toronto Area"}}
    out = apply(engine(local={"label": [rule]}), mississauga_result())
    assert out.regions[0].name == "Greater Toronto Area" and out.regions[0].kind.value == "region"
    assert out.sources["regions"] == "override:local:local.toml#1"
