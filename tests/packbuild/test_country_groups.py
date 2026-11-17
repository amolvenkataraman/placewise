"""The country-group generator: validation of the curated datasets and the generated module."""

import copy
import json
from pathlib import Path

import pytest
from datasets_kit import needs_datasets

from packbuild import country_groups as cg

pytestmark = needs_datasets

REPO = Path(__file__).resolve().parents[2]
GENERATED = REPO / "src" / "placewise" / "constants" / "countries" / "groups.py"


@pytest.fixture(scope="module")
def datasets():
    return cg.load(cg.DATASETS)


def test_the_curated_datasets_are_valid(datasets):
    geographic, legal = datasets
    assert cg.validate(geographic, legal) == []


def test_the_generated_module_is_in_sync_with_the_json(tmp_path):
    out = tmp_path / "groups.py"
    cg.main(["--out", str(out)])
    assert out.read_text(encoding="utf-8") == GENERATED.read_text(encoding="utf-8")


def test_check_mode_passes_on_the_committed_module():
    assert cg.main(["--check", "--out", str(GENERATED)]) == 0


def test_check_mode_fails_on_a_stale_module(tmp_path):
    stale = tmp_path / "groups.py"
    stale.write_text("# stale\n", encoding="utf-8")
    assert cg.main(["--check", "--out", str(stale)]) == 1


def test_the_generated_module_says_where_it_comes_from(datasets):
    text = cg.render(*datasets)
    assert text.startswith(
        '"""GENERATED from datasets/country_groups by packbuild.country_groups; do not edit'
    )


def test_iso_codes_come_from_the_package_table():
    codes = cg.iso_alpha2()
    assert len(codes) == 249 and {"US", "CA", "GB", "NA", "AQ", "TW"} <= codes
    assert "XK" not in codes and "EU" not in codes and "UK" not in codes


# Each check is shown failing on a small, deliberately broken copy of the real data.


def _broken(datasets, mutate):
    geographic, legal = copy.deepcopy(datasets)
    mutate(geographic, legal)
    return cg.validate(geographic, legal)


def _group(data, gid):
    return next(g for g in data["groups"] if g["id"] == gid)


def test_unknown_iso_code_is_reported(datasets):
    errors = _broken(datasets, lambda g, _: _group(g, "geo:dach")["members"].append("UK"))
    assert any("geo:dach" in e and "UK" in e for e in errors)


def test_unknown_legal_member_code_is_reported(datasets):
    errors = _broken(datasets, lambda _, lg: _group(lg, "legal:eu")["members"].append({"code": "XK"}))
    assert any("legal:eu" in e and "XK" in e for e in errors)


def test_duplicate_ids_are_reported(datasets):
    def mutate(geographic, _):
        geographic["groups"].append({**_group(geographic, "geo:dach"), "aliases": [], "name": "Copy"})

    assert any("duplicate id" in e and "geo:dach" in e for e in _broken(datasets, mutate))


def test_alias_collisions_across_groups_are_reported(datasets):
    def mutate(geographic, legal):
        _group(geographic, "geo:benelux")["aliases"].append("eu")  # case-insensitive clash with legal:eu

    errors = _broken(datasets, mutate)
    assert any("alias" in e and "'eu'" in e for e in errors)


def test_a_name_counts_as_an_alias(datasets):
    errors = _broken(datasets, lambda g, _: _group(g, "geo:baltics")["aliases"].append("Benelux"))
    assert any("'benelux'" in e for e in errors)


def test_duplicate_members_are_reported(datasets):
    errors = _broken(datasets, lambda g, _: _group(g, "geo:us-canada")["members"].append("US"))
    assert any("geo:us-canada" in e and "duplicate member" in e for e in errors)


def test_bad_kind_is_reported(datasets):
    def mutate(geographic, _):
        _group(geographic, "geo:dach")["kind"] = "union"  # a legal kind in the geographic file

    assert any("geo:dach" in e and "kind" in e for e in _broken(datasets, mutate))


@pytest.mark.parametrize("since", ["2020-02-30", "20", "2020/01/01", "1995-1-1"])
def test_bad_dates_are_reported(datasets, since):
    errors = _broken(datasets, lambda _, lg: _group(lg, "legal:nato")["members"][0].update(since=since))
    assert any("legal:nato" in e and "date" in e for e in errors)


def test_until_before_since_is_reported(datasets):
    def mutate(_, legal):
        _group(legal, "legal:eu")["members"].append({"code": "NO", "since": "2000", "until": "1999-01-01"})

    assert any("legal:eu" in e and "NO" in e for e in _broken(datasets, mutate))


def test_unknown_group_reference_is_reported(datasets):
    errors = _broken(
        datasets, lambda _, lg: _group(lg, "legal:g20")["members"].append({"group": "legal:nope"})
    )
    assert any("legal:nope" in e for e in errors)


def test_missing_source_is_reported(datasets):
    errors = _broken(datasets, lambda _, lg: _group(lg, "legal:gcc").update(source="somewhere"))
    assert any("legal:gcc" in e and "source" in e for e in errors)


def test_as_of_is_required(datasets):
    errors = _broken(datasets, lambda _, lg: lg.pop("as_of"))
    assert any("as_of" in e for e in errors)


def test_main_refuses_to_write_invalid_data(tmp_path):
    src = tmp_path / "country_groups"
    src.mkdir()
    for name in ("geographic.json", "legal.json"):
        (src / name).write_text((cg.DATASETS / name).read_text(encoding="utf-8"), encoding="utf-8")
    geographic = json.loads((src / "geographic.json").read_text(encoding="utf-8"))
    geographic["groups"][0]["members"].append("ZZ")
    (src / "geographic.json").write_text(json.dumps(geographic), encoding="utf-8")
    out = tmp_path / "groups.py"
    assert cg.main(["--datasets", str(src), "--out", str(out)]) == 1
    assert not out.exists()
