"""placewise.overrides.rules.regions: city and region rules."""

import json

from overrides_kit import (
    DATA_BAY_AREA,
    GTA_MEMBERS,
    OAKLAND,
    SAN_FRANCISCO,
    TORONTO,
    apply,
    engine,
    mississauga_result,
    oakland_result,
    sf_result,
    toronto_result,
    write,
)

from placewise.overrides import load_overrides


def test_city_rule_by_locality_replaces_the_display_city():
    eng = engine(repo={"city": [{"locality": OAKLAND.id, "city": "Bay Area"}]})
    out = apply(eng, oakland_result())
    assert out.city.name == "Bay Area"
    assert out.city.id != OAKLAND.id  # a different entity than the City of Oakland
    assert out.locality == OAKLAND
    assert out.sources["city"] == "override:repo:repo.toml#1"
    assert apply(eng, sf_result()).city == SAN_FRANCISCO


def test_city_rule_by_area():
    bay = {"bbox": {"south": 37.2, "west": -122.6, "north": 38.3, "east": -121.6}}
    eng = engine(local={"city": [{"within": bay, "city": "Bay Area"}]})
    assert apply(eng, sf_result()).city.name == "Bay Area"
    assert apply(eng, oakland_result()).city.name == "Bay Area"
    assert apply(eng, toronto_result()).city == TORONTO


def test_region_rule_adds_members_and_leaves_others():
    eng = engine(repo={"region": [{"id": "region:gta", "label": "GTA", "members": GTA_MEMBERS}]})
    out = apply(eng, mississauga_result())
    assert [r.name for r in out.regions] == ["GTA"]
    assert out.regions[0].id == "region:gta" and out.regions[0].kind.value == "region"
    assert out.sources["regions"] == "override:repo:repo.toml#1"
    assert apply(eng, toronto_result()).regions[0].id == "region:gta"
    assert apply(eng, oakland_result()) == oakland_result()


def test_region_rule_redefines_a_data_region():
    # the rule's membership is authoritative: a point outside it loses the data region
    redefine = {"id": DATA_BAY_AREA.id, "label": "Bay Area", "members": {"id": [SAN_FRANCISCO.id]}}
    eng = engine(repo={"region": [redefine]})
    assert apply(eng, oakland_result()).regions == ()
    assert apply(eng, sf_result()).regions[0].name == "Bay Area"
    relabel = {"id": DATA_BAY_AREA.id, "label": "Bay Area", "members": {"id": [OAKLAND.id, SAN_FRANCISCO.id]}}
    out = apply(engine(repo={"region": [relabel]}), oakland_result())
    assert [r.name for r in out.regions] == ["Bay Area"]


def test_region_rule_remove_and_polygon(tmp_path):
    out = apply(engine(local={"region": [{"id": DATA_BAY_AREA.id, "remove": True}]}), oakland_result())
    assert out.regions == () and out.sources["regions"] == "override:local:local.toml#1"

    (tmp_path / "east_bay.geojson").write_text(
        json.dumps(
            {
                "type": "Polygon",
                "coordinates": [[[-122.35, 37.70], [-122.0, 37.70], [-122.0, 37.95], [-122.35, 37.95]]],
            }
        )
    )
    write(
        tmp_path / "local.json",
        {"region": [{"id": "local:east-bay", "label": "East Bay", "polygon": "east_bay.geojson"}]},
    )
    (tmp_path / "repo").mkdir()
    eng = load_overrides(repo_dir=tmp_path / "repo", local_path=tmp_path / "local.json")
    assert [r.name for r in apply(eng, oakland_result()).regions] == ["San Francisco Bay Area", "East Bay"]
    assert apply(eng, sf_result()).regions == ()
