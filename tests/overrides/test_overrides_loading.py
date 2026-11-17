"""placewise.overrides.loading: the repo / app / local layers, their files and the errors that name them."""

import dataclasses

import pytest
from overrides_kit import (
    KARIYA_PARK,
    MISSISSAUGA,
    TORONTO,
    apply,
    mississauga_result,
    needs_toml,
    toronto_result,
    write,
)

from placewise.overrides import REPO_DIR, load_overrides


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
            "alias": [{"text": "GTA", "means": "region:gta"}],
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
            "alias": [{"text": "gta", "means": "region:gtha"}],
        },
    )
    eng = load_overrides(repo_dir=empty_repo, local_path=local)
    port_credit = dataclasses.replace(mississauga_result(), lat=43.5503, lon=-79.5868)
    out = apply(eng, port_credit)
    assert out.sublocality.name == "Port Credit Village"
    assert out.sources["sublocality"] == "override:local:overrides.json#1"
    assert eng.resolve_name("GTA") == ["region:gtha", "region:gta"]


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


def test_shipped_repo_overrides_load(tmp_path):
    eng = load_overrides(local_path=False)
    assert REPO_DIR.is_dir()
    assert eng.resolve_name("GTA") == ["region:gta"]
    assert eng.resolve_name("Bay Area") == ["region:sf-bay-area"]
    assert all(r["origin"].startswith("repo:") for r in eng.explain())


@needs_toml
def test_shipped_toml_and_its_json_twin_agree():
    from placewise.config import _toml

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

    from placewise.config import _toml

    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", None)
    eng = load_overrides(local_path=False)
    assert eng.resolve_name("GTA") == ["region:gta"]
    assert eng.rules[0].origin == "repo:aliases.toml#1"
    # a TOML file with no twin, or a TOML local file, gets the clear error
    local = tmp_path / "overrides.toml"
    local.write_text("")
    with pytest.raises(_toml.TomlUnavailableError, match="pip install tomli"):
        load_overrides(local_path=local)
