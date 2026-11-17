"""packbuild.regions: datasets/regions -> constants/countries/regions.py."""

import json

import pytest

from packbuild import regions


def test_generated_module_matches_the_dataset():
    assert regions.MODULE.read_text(encoding="utf-8") == regions.render(regions.load()), (
        "constants/countries/regions.py is out of date: run python -m packbuild.regions"
    )


def test_check_flag(capsys):
    assert regions.main(["--check"]) == 0


def _region(**overrides):
    entry = {
        "id": "placewise:region/test-metro",
        "short_name": "Test Metro",
        "name": "Test metropolitan area",
        "country": "CA",
        "admin1": ["ON"],
        "aliases": ["Test Area"],
        "members": [],
        "principal_cities": {"Testville": "ON"},
        "city_aliases": {"TV": "Testville"},
        "notes": "for tests",
    }
    return {**entry, **overrides}


def _write(tmp_path, *entries):
    (tmp_path / "can.json").write_text(json.dumps({"regions": list(entries)}))
    return tmp_path


def test_render_round_trips(tmp_path):
    loaded = regions.load(_write(tmp_path, _region()))
    namespace = {}
    text = regions.render(loaded).replace(
        "from ._records import Metro", "from placewise.constants.countries import Metro"
    )
    exec(compile(text, "regions.py", "exec"), namespace)
    (metro,) = namespace["REGIONS"]
    assert (metro.id, metro.key, metro.admin1, metro.cities) == (
        "placewise:region/test-metro",
        "Test Metro",
        ("ON",),
        {"Testville": "ON"},
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "region/test"}, "id must be"),
        ({"country": "XX"}, "unknown country"),
        ({"admin1": ["ZZ"], "principal_cities": {}}, "unknown admin1"),
        ({"members": ["Toronto"]}, "not a pack id"),
        ({"principal_cities": {"Testville": "BC"}}, "doesn't reach"),
        ({"city_aliases": {"TV": "Nowhere"}}, "not a principal city"),
        ({"colour": "red"}, "unknown fields"),
    ],
)
def test_validation(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        regions.load(_write(tmp_path, _region(**overrides)))


def test_names_must_be_unique(tmp_path):
    second = _region(
        id="placewise:region/other", short_name="Other", name="Other area", aliases=["Test Area"]
    )
    second.pop("city_aliases")
    with pytest.raises(ValueError, match="also names"):
        regions.load(_write(tmp_path, _region(), second))
