"""placewise.store.coverage: which pack serves which country and kind of answer, from the index
entry, from pack.json, or (for older indexes and packs) from the pack's name and layers."""

import pytest

from placewise.store.coverage import Coverage, derive, from_entry


@pytest.mark.parametrize(
    ("name", "kind", "covers", "requires"),
    [
        ("world", "base", ("*",), ()),
        ("usa", "country", ("US",), ()),
        ("us", "country", ("US",), ()),  # the older two-letter names
        ("can", "country", ("CA",), ()),
        ("ind", "country", ("IN",), ()),
        ("usa-parks", "parks", ("US",), ()),
        ("usa-parks-local", "parks", ("US",), ()),
        ("can-parks", "parks", ("CA",), ()),
        ("usa-zip", "postal", ("US",), ("usa",)),
        ("world-water", "water", ("*",), ()),
        ("world-postal", "postal", ("*",), ()),  # pack.json lists the countries it covers
        ("world-parks", "parks", ("*",), ()),
        ("world-notable", "notable", ("*",), ()),
        ("world-notable-sa", "notable", ("*",), ()),
        ("world-towns", "towns", ("*",), ()),
    ],
)
def test_derived_from_the_name(name, kind, covers, requires):
    assert derive(name) == Coverage(kind=kind, covers=covers, requires=requires)


def test_layers_name_the_kind_when_the_name_does_not():
    assert derive("mystery", {"layers": ["marine", "lakes"]}).kind == "water"
    assert derive("mystery", {"layers": ["reservoirs"]}).kind == "water"
    assert derive("mystery", {"layers": ["postal"]}).kind == "postal"
    assert derive("mystery", {"layers": ["parks_national"]}).kind == "parks"
    assert derive("mystery", {"layers": ["cities"]}).kind == "other"
    assert derive("mystery").covers == ()


def test_pack_json_fields_win_and_give_the_installed_size():
    manifest = {
        "name": "usa-zip",
        "layers": ["zcta"],
        "kind": "postal",
        "covers": ["US", "PR"],
        "requires": ["usa"],
        "files": {"a": {"sha256": "0" * 64, "size": 100}, "b": {"sha256": "1" * 64, "size": 23}},
    }
    cov = derive("usa-zip", manifest, manifest_bytes=77)
    assert (cov.kind, cov.covers, cov.requires) == ("postal", ("PR", "US"), ("usa",))
    assert cov.installed_bytes == 200


def test_index_entries_carry_the_fields_and_fall_back_to_the_name():
    entry = {"kind": "parks", "covers": ["US"], "requires": [], "installed_bytes": 5}
    assert from_entry("usa-parks", entry) == Coverage("parks", ("US",), (), 5)
    assert from_entry("usa", {}) == Coverage("country", ("US",), ())
    with pytest.raises(ValueError, match="covers"):
        from_entry("usa", {"covers": "US"})
    with pytest.raises(ValueError, match="kind"):
        from_entry("usa", {"kind": 3})


def test_serves_countries_or_everywhere():
    assert derive("usa").serves({"US", "CA"}) and not derive("usa").serves({"CA"})
    assert derive("world-water").serves(set()) and derive("world-water").serves({"FR"})
    assert derive("world-water").worldwide and not derive("usa").worldwide
