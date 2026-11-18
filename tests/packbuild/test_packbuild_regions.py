"""packbuild.regions: datasets/regions -> constants/countries/regions.py."""

import json

import pytest
from datasets_kit import needs_datasets

from packbuild import regions


@needs_datasets
def test_generated_module_matches_the_dataset():
    assert regions.MODULE.read_text(encoding="utf-8") == regions.render(regions.load()), (
        "constants/countries/regions.py is out of date: run python -m packbuild.regions"
    )


@needs_datasets
def test_check_flag(capsys):
    assert regions.main(["--check"]) == 0


def _region(**overrides):
    entry = {
        "id": "region:test-metro",
        "short_name": "Test Metro",
        "name": "Test metropolitan area",
        "country": "CA",
        "admin1": ["ON"],
        "aliases": ["Test Area"],
        "kind": "metro",
        "members": ["statcan:3520"],
        "definition": {"title": "A test definition", "url": "https://example.org/test"},
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
        "region:test-metro",
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
        ({"id": "placewise:region/test"}, "id must be"),
        ({"kind": "city"}, "kind 'city'"),
        ({"definition": {"title": "No link"}}, "definition must be"),
        ({"definition": {"title": "Plain", "url": "http://example.org"}}, "definition must be"),
        ({"members": ["statcan:3520", "statcan:3520"]}, "listed twice"),
        ({"districts": {"BC": ["SOMEWHERE"]}}, "districts of 'BC'"),
        ({"lgd_units": ["taluka:4165"]}, "lgd_units"),
        ({"lgd_units": []}, "lgd_units"),
        ({"search_as": "region:nowhere"}, "search_as must name"),
    ],
)
def test_validation(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        regions.load(_write(tmp_path, _region(**overrides)))


@needs_datasets
def test_every_dataset_region_has_a_kind_and_a_cited_definition():
    for r in regions.load():
        assert r["kind"] in regions.KINDS
        assert r["definition"]["url"].startswith("https://") and r["definition"]["title"]


def test_pin_ids_are_pack_ids(tmp_path):
    (r,) = regions.load(
        _write(
            tmp_path,
            _region(
                country="IN", admin1=["DL"], principal_cities={}, city_aliases={}, members=["pin:110001"]
            ),
        )
    )
    assert r["members"] == ["pin:110001"]


def test_india_regions_may_name_lgd_districts_and_sub_districts(tmp_path):
    (r,) = regions.load(
        _write(
            tmp_path,
            _region(country="IN", admin1=["MH"], principal_cities={}, city_aliases={}, members=["pin:400001"],
                    lgd_units=["district:482", "subdistrict:4165"]),
        )
    )  # fmt: skip
    assert r["lgd_units"] == ["district:482", "subdistrict:4165"]


def test_names_must_be_unique(tmp_path):
    second = _region(id="region:other", short_name="Other", name="Other area", aliases=["Test Area"])
    second.pop("city_aliases")
    with pytest.raises(ValueError, match="also names"):
        regions.load(_write(tmp_path, _region(), second))


def _folded():
    return _region(
        id="region:test-wider",
        short_name="TWA",
        name="Test wider area",
        aliases=["Test and Beyond"],
        search_as="region:test-metro",
        principal_cities={},
        city_aliases={},
    )


def test_a_region_read_as_another_folds_its_names_into_that_entry(tmp_path):
    loaded = regions.load(_write(tmp_path, _region(), _folded()))
    (entry,) = regions.searchable(loaded)
    assert entry["id"] == "region:test-metro"
    assert entry["aliases"] == ["Test Area", "TWA", "Test wider area", "Test and Beyond"]
    assert "region:test-wider" not in regions.render(loaded)
    assert len(loaded) == 2  # both are still drawn in the packs


def test_a_region_read_as_another_may_share_its_names_but_lists_no_cities(tmp_path):
    regions.load(_write(tmp_path, _region(), _folded() | {"aliases": ["Test Area"]}))
    with pytest.raises(ValueError, match="lists no cities"):
        regions.load(_write(tmp_path, _region(), _folded() | {"principal_cities": {"Testville": "ON"}}))
    with pytest.raises(ValueError, match="search_as must name"):
        regions.load(_write(tmp_path, _region(search_as="region:test-metro")))
