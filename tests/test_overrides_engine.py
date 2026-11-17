"""placewise.overrides: loading the repo / app / local layers and applying them to a lookup Result.

Every Result here is built by hand from public places, so no packs are needed.
"""

import dataclasses
import importlib.util
import json

import pytest

from placewise.model import Layer, Nearby, Place, Result
from placewise.overrides import REPO_DIR, OverrideEngine, load_overrides

HAS_TOML = any(importlib.util.find_spec(name) for name in ("tomllib", "tomli"))
needs_toml = pytest.mark.skipif(not HAS_TOML, reason="needs tomllib (3.11+) or tomli")

# --- public places -----------------------------------------------------------------------------

CANADA = Place("wikidata:Q16", "Canada", "country", codes={"iso2": "CA"})
ONTARIO = Place("wikidata:Q1904", "Ontario", "admin1", codes={"iso2": "CA-ON"})
PEEL = Place("statcan:cd:3521", "Peel", "admin2", codes={"ca_cd": "3521"})
TORONTO_DIV = Place("statcan:cd:3520", "Toronto", "admin2", codes={"ca_cd": "3520"})
MISSISSAUGA = Place("wikidata:Q50816", "Mississauga", "locality")
TORONTO = Place("wikidata:Q172", "Toronto", "locality")
KARIYA_PARK = Place("osm:way/kariya-park", "Kariya Park", "park", tier=3)
LAKE_ONTARIO = Place("wikidata:Q1062", "Lake Ontario", "water")
RATTRAY_MARSH = Place("osm:way/rattray-marsh", "Rattray Marsh", "park", tier=3)
PEARSON = Place("wikidata:Q29415", "Toronto Pearson International Airport", "airport", codes={"iata": "YYZ"})

USA = Place("wikidata:Q30", "United States", "country", codes={"iso2": "US"})
CALIFORNIA = Place("wikidata:Q99", "California", "admin1", codes={"iso2": "US-CA"})
ALAMEDA = Place("wikidata:Q107146", "Alameda County", "admin2")
OAKLAND = Place("wikidata:Q17042", "Oakland", "locality")
SAN_FRANCISCO = Place("wikidata:Q62", "San Francisco", "locality")
DATA_BAY_AREA = Place("wikidata:Q213205", "San Francisco Bay Area", "region")

MISSISSAUGA_PT = (43.5890, -79.6441)  # Mississauga Civic Centre
TORONTO_PT = (43.6532, -79.3832)  # Toronto City Hall
OAKLAND_PT = (37.8053, -122.2725)  # Oakland City Hall
SF_PT = (37.7793, -122.4193)  # San Francisco City Hall


def mississauga_result():
    return Result(
        *MISSISSAUGA_PT,
        label="Mississauga, Ontario",
        country=CANADA,
        admin1=ONTARIO,
        admin2=PEEL,
        city=MISSISSAUGA,
        locality=MISSISSAUGA,
        within=(KARIYA_PARK,),
        near=(Nearby(LAKE_ONTARIO, "near", 4.0), Nearby(RATTRAY_MARSH, "near", 6.0)),
        airport=Nearby(PEARSON, "near", 7.0),
        sources={"locality": "data:ca-2026.11"},
    )


def toronto_result():
    return Result(
        *TORONTO_PT,
        label="Toronto, Ontario",
        country=CANADA,
        admin1=ONTARIO,
        admin2=TORONTO_DIV,
        city=TORONTO,
        locality=TORONTO,
    )


def oakland_result():
    return Result(
        *OAKLAND_PT,
        label="Oakland, California",
        country=USA,
        admin1=CALIFORNIA,
        admin2=ALAMEDA,
        city=OAKLAND,
        locality=OAKLAND,
        regions=(DATA_BAY_AREA,),
    )


def sf_result():
    return Result(
        *SF_PT,
        label="San Francisco, California",
        country=USA,
        admin1=CALIFORNIA,
        city=SAN_FRANCISCO,
        locality=SAN_FRANCISCO,
    )


def engine(**layers):
    """An engine from in-memory documents: engine(repo={...}, app={...}, local={...})."""
    return OverrideEngine.from_documents(
        [(Layer(name), doc, f"{name}:{name}.toml") for name, doc in layers.items()]
    )


def apply(eng, result):
    return eng.apply(result, result.lat, result.lon)


@pytest.fixture
def empty_repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    return d


def write(path, doc):
    path.write_text(json.dumps(doc))
    return path


# --- loading, precedence, origins ---------------------------------------------------------------


def test_layers_load_from_repo_dir_app_dicts_and_local_file(tmp_path, empty_repo):
    write(empty_repo / "naming.json", {"rename": [{"id": MISSISSAUGA.id, "name": "Sauga"}]})
    eng = load_overrides(repo_dir=empty_repo, local_path=False)
    out = apply(eng, mississauga_result())
    assert out.locality.name == "Sauga"
    assert out.sources["locality"] == "override:repo:naming.json#1"

    app = {"rename": [{"id": MISSISSAUGA.id, "name": "City of Mississauga"}]}
    eng = load_overrides(repo_dir=empty_repo, local_path=False, app_rules=app)
    out = apply(eng, mississauga_result())
    assert out.locality.name == "City of Mississauga"
    assert out.sources["locality"] == "override:app#1"

    local = write(
        tmp_path / "overrides.json", {"rename": [{"id": MISSISSAUGA.id, "name": "Mississauga, ON"}]}
    )
    eng = load_overrides(repo_dir=empty_repo, local_path=local, app_rules=app)
    out = apply(eng, mississauga_result())
    assert out.locality.name == "Mississauga, ON"
    assert out.sources["locality"] == "override:local:overrides.json#1"


def test_precedence_is_by_layer_not_load_order():
    eng = OverrideEngine.from_documents(
        [
            (Layer.LOCAL, {"rename": [{"id": TORONTO.id, "name": "local"}]}, "local:o.toml"),
            (Layer.REPO, {"rename": [{"id": TORONTO.id, "name": "repo"}]}, "repo:r.toml"),
            (Layer.APP, {"rename": [{"id": TORONTO.id, "name": "app"}]}, "app"),
        ]
    )
    assert apply(eng, toronto_result()).locality.name == "local"
    assert [r.origin for r in eng.rules] == ["repo:r.toml#1", "app#1", "local:o.toml#1"]


def test_within_a_layer_the_later_rule_wins():
    eng = engine(repo={"rename": [{"id": TORONTO.id, "name": "first"}, {"id": TORONTO.id, "name": "second"}]})
    out = apply(eng, toronto_result())
    assert out.locality.name == "second"
    assert out.sources["locality"] == "override:repo:repo.toml#2"


def test_local_file_overrides_a_repo_rule(tmp_path, empty_repo):
    write(
        empty_repo / "areas.json",
        {
            "label": [
                {
                    "within": {"point": {"lat": 43.5503, "lon": -79.5868}, "km": 1.0},
                    "fields": {"sublocality": "Port Credit"},
                }
            ],
            "alias": [{"text": "GTA", "means": "placewise:region/gta"}],
        },
    )
    local = write(
        tmp_path / "overrides.json",
        {
            "label": [
                {
                    "within": {"point": {"lat": 43.5503, "lon": -79.5868}, "km": 1.0},
                    "fields": {"sublocality": "Port Credit Village"},
                }
            ],
            "alias": [{"text": "gta", "means": "placewise:region/gtha"}],
        },
    )
    eng = load_overrides(repo_dir=empty_repo, local_path=local)
    port_credit = dataclasses.replace(mississauga_result(), lat=43.5503, lon=-79.5868)
    out = apply(eng, port_credit)
    assert out.sublocality.name == "Port Credit Village"
    assert out.sources["sublocality"] == "override:local:overrides.json#1"
    assert eng.resolve_name("GTA") == ["placewise:region/gtha", "placewise:region/gta"]


def test_default_local_path_is_the_store_overrides_file(tmp_path, monkeypatch, empty_repo):
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path))
    write(tmp_path / "overrides.json", {"hide": [{"id": KARIYA_PARK.id}]})  # JSON twin of overrides.toml
    eng = load_overrides(repo_dir=empty_repo)
    assert apply(eng, mississauga_result()).within == ()
    assert eng.rules[0].origin == "local:overrides.json#1"


@needs_toml
def test_toml_local_file(tmp_path, empty_repo):
    local = tmp_path / "overrides.toml"
    local.write_text(f'[[rename]]\nid = "{TORONTO.id}"\nname = "The 6ix"\n')
    out = apply(load_overrides(repo_dir=empty_repo, local_path=local), toronto_result())
    assert out.locality.name == "The 6ix"
    assert out.sources["locality"] == "override:local:overrides.toml#1"


def test_apply_returns_a_new_result_and_leaves_the_input_alone():
    before = mississauga_result()
    eng = engine(repo={"rename": [{"id": MISSISSAUGA.id, "name": "Sauga"}]})
    out = apply(eng, before)
    assert before == mississauga_result()
    assert out is not before and out.locality.name == "Sauga"
    assert apply(OverrideEngine.from_documents([]), before) == before
    # data sources for untouched fields are kept
    assert out.sources["locality"].startswith("override:") and "admin1" not in out.sources


# --- rule types ---------------------------------------------------------------------------------


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


def test_relabel_hook_recomposes_the_label_after_name_changes():
    eng = engine(repo={"rename": [{"id": MISSISSAUGA.id, "name": "Sauga"}]})
    out = eng.apply(
        mississauga_result(), *MISSISSAUGA_PT, relabel=lambda r: f"{r.locality.name}, {r.admin1.name}"
    )
    assert out.label == "Sauga, Ontario"
    assert out.sources["label"] == "override:repo:repo.toml#1"


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


GTA_MEMBERS = {"ca_cd": ["3518", "3519", "3520", "3521", "3524"]}


def test_region_rule_adds_members_and_leaves_others():
    eng = engine(repo={"region": [{"id": "placewise:region/gta", "label": "GTA", "members": GTA_MEMBERS}]})
    out = apply(eng, mississauga_result())
    assert [r.name for r in out.regions] == ["GTA"]
    assert out.regions[0].id == "placewise:region/gta" and out.regions[0].kind.value == "region"
    assert out.sources["regions"] == "override:repo:repo.toml#1"
    assert apply(eng, toronto_result()).regions[0].id == "placewise:region/gta"
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


def test_tune_sets_tier_and_trims_near_entries():
    eng = engine(repo={"tune": [{"id": KARIYA_PARK.id, "tier": 2}, {"kind": "park", "near_km": 5}]})
    out = apply(eng, mississauga_result())
    assert out.within[0].tier == 2 and out.sources["within"] == "override:repo:repo.toml#1"
    assert [n.place.id for n in out.near] == [LAKE_ONTARIO.id]  # Rattray Marsh is 6 km off
    assert out.sources["near"] == "override:repo:repo.toml#2"


def test_tune_knobs_merge_by_precedence():
    eng = engine(
        repo={"tune": [{"kind": "park", "near_km": 5, "boost": 1.5}]},
        local={"tune": [{"id": RATTRAY_MARSH.id, "near_km": 10}]},
    )
    out = apply(eng, mississauga_result())
    assert [n.place.id for n in out.near] == [LAKE_ONTARIO.id, RATTRAY_MARSH.id]
    assert eng.tuning(RATTRAY_MARSH) == {"near_km": 10.0, "boost": 1.5}
    assert eng.tuning(KARIYA_PARK) == {"near_km": 5.0, "boost": 1.5}
    assert eng.tuning(LAKE_ONTARIO) == {}
    assert eng.tuning(id=RATTRAY_MARSH.id) == {"near_km": 10.0}
    assert eng.tuning(kind="park") == {"near_km": 5.0, "boost": 1.5}


def test_resolve_name_returns_alias_targets():
    eng = engine(
        repo={
            "alias": [
                {"text": "GTA", "means": "placewise:region/gta"},
                {"text": "The Bay", "means": DATA_BAY_AREA.id, "country": "US"},
            ],
            "rename": [{"id": MISSISSAUGA.id, "name": "Sauga", "aliases": ["The Sauga"]}],
            "region": [
                {"id": "placewise:region/905", "label": "The 905", "aliases": ["905"], "members": GTA_MEMBERS}
            ],
        }
    )
    assert eng.resolve_name("gta") == ["placewise:region/gta"]
    assert eng.resolve_name("  the   bay ") == [DATA_BAY_AREA.id]
    assert eng.resolve_name("The Bay", country="CA") == []
    assert eng.resolve_name("The Bay", country="US") == [DATA_BAY_AREA.id]
    assert eng.resolve_name("the sauga") == [MISSISSAUGA.id]
    assert eng.resolve_name("905") == ["placewise:region/905"]
    assert eng.resolve_name("Narnia") == []


def test_explain_lists_rules_with_origins():
    eng = engine(
        repo={"alias": [{"text": "GTA", "means": "placewise:region/gta"}]},
        local={"hide": [{"id": KARIYA_PARK.id}]},
    )
    rows = eng.explain()
    assert [(r["layer"], r["type"], r["origin"]) for r in rows] == [
        ("repo", "alias", "repo:repo.toml#1"),
        ("local", "hide", "local:local.toml#1"),
    ]
    assert rows[0]["rule"] == {"text": "GTA", "means": "placewise:region/gta"}


# --- errors -------------------------------------------------------------------------------------


def test_unknown_rule_type_names_file_and_rule_number(tmp_path, empty_repo):
    write(empty_repo / "bad.json", {"alias": [{"text": "a", "means": "b"}], "colour": [{"id": "x"}]})
    with pytest.raises(ValueError, match=r"bad\.json.*#2.*colour"):
        load_overrides(repo_dir=empty_repo, local_path=False)


def test_bad_field_names_file_and_rule_number(tmp_path, empty_repo):
    local = write(tmp_path / "mine.json", {"hide": [{"id": "a"}, {"id": "b"}, {"idd": "c"}]})
    with pytest.raises(ValueError, match=r"mine\.json.*#3.*idd"):
        load_overrides(repo_dir=empty_repo, local_path=local)
    local = write(
        tmp_path / "mine.json", {"label": [{"within": {"country": "CA"}, "fields": {"colour": "red"}}]}
    )
    with pytest.raises(ValueError, match=r"mine\.json.*#1.*colour"):
        load_overrides(repo_dir=empty_repo, local_path=local)


def test_missing_named_dirs_and_files_are_errors(tmp_path, empty_repo):
    with pytest.raises(FileNotFoundError, match="nope"):
        load_overrides(repo_dir=tmp_path / "nope", local_path=False)
    with pytest.raises(FileNotFoundError, match="typo"):
        load_overrides(repo_dir=empty_repo, local_path=tmp_path / "typo.toml")


def test_a_missing_default_local_file_is_fine(tmp_path, monkeypatch, empty_repo):
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path / "fresh"))
    assert len(load_overrides(repo_dir=empty_repo)) == 0


def test_app_rule_errors_name_the_app_layer(empty_repo, tmp_path):
    with pytest.raises(ValueError, match=r"app.*#1"):
        load_overrides(repo_dir=empty_repo, local_path=False, app_rules={"add": [{"name": "x"}]})


# --- the shipped repo layer ---------------------------------------------------------------------


def test_shipped_repo_overrides_load(tmp_path):
    eng = load_overrides(local_path=False)
    assert REPO_DIR.is_dir()
    assert eng.resolve_name("GTA") == ["placewise:region/gta"]
    assert eng.resolve_name("Bay Area") == ["placewise:region/sf-bay-area"]
    assert all(r["origin"].startswith("repo:") for r in eng.explain())


@needs_toml
def test_shipped_toml_and_its_json_twin_agree():
    from placewise import _toml

    tomls = sorted(REPO_DIR.glob("*.toml"))
    assert tomls, "the repo layer ships at least one TOML file"
    for path in tomls:
        twin = path.with_suffix(".json")
        assert twin.exists(), f"{path.name} needs a JSON twin for Python 3.10 without tomli"
        assert _toml.load(path) == _toml.load(twin), (
            f"{twin.name} is out of date; regenerate it from {path.name} (see docs/overrides.md)"
        )


def test_without_a_toml_parser_the_repo_layer_reads_json_twins_and_cites_the_toml(monkeypatch, tmp_path):
    import sys

    from placewise import _toml

    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", None)
    eng = load_overrides(local_path=False)
    assert eng.resolve_name("GTA") == ["placewise:region/gta"]
    assert eng.rules[0].origin == "repo:aliases.toml#1"
    # a TOML file with no twin, or a TOML local file, gets the clear error
    local = tmp_path / "overrides.toml"
    local.write_text("")
    with pytest.raises(_toml.TomlUnavailableError, match="pip install tomli"):
        load_overrides(local_path=local)
