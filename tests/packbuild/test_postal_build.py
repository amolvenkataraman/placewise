# ruff: noqa: E501  (data rows are longer than a line)
"""packbuild.postal: the optional world-postal pack from GeoNames' postal codes, offline."""

import json
import zipfile

import pytest

from packbuild import postal
from packbuild.sources import url
from placewise.constants import postal as const
from placewise.packs import open_pack

# fmt: off
ROWS = [
    ("FR", "75007", "Paris 07", "Île-de-France", "11", "Paris", "75", "", "", "48.8565", "2.321", "5"),
    ("DE", "10117", "Berlin", "Land Berlin", "BE", "", "00", "", "", "52.517", "13.3872", "6"),
    ("CZ", "100 00", "Praha 10", "Hlavní město Praha", "", "", "", "", "", "50.0673", "14.4603", "4"),
    ("GB", "SW1A", "Westminster Abbey", "England", "ENG", "Greater London", "", "", "", "51.5018", "-0.1328", "1"),
    ("AU", "2000", "Sydney", "New South Wales", "NSW", "Sydney", "", "", "", "-33.8703", "151.2073", "6"),
    ("AU", "2000", "The Rocks", "New South Wales", "NSW", "Sydney", "", "", "", "-33.8605", "151.2073", "6"),
    ("US", "10001", "New York", "New York", "NY", "", "", "", "", "40.75", "-73.99", "4"),
]
# fmt: on


@pytest.fixture
def built(tmp_path, monkeypatch):
    archive = tmp_path / "src" / "allCountries.zip"
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("allCountries.txt", "".join("\t".join(r) + "\n" for r in ROWS))
    asked = []

    def fake_fetch(link, cache_dir, refresh=False, timeout=60):
        asked.append((link, cache_dir))
        return archive

    monkeypatch.setattr(postal, "fetch", fake_fetch)
    path = postal.build(tmp_path / "cache", tmp_path / "out", "2026.11")
    return path, asked, tmp_path


def test_build_writes_the_postal_points_from_the_registry_download(built):
    path, asked, tmp_path = built
    assert path == tmp_path / "out" / "world-postal-2026.11"
    assert asked == [(url("geonames", "postal_world"), tmp_path / "cache" / "geonames-postal")]
    pack = open_pack(path)
    assert pack.name == const.PACK and [layer.name for layer in pack] == [const.LAYER]
    layer = pack[const.LAYER]
    assert layer.kind == "point" and layer.count == 6  # the US row is left out
    # the codes column only feeds the name index; it is not written
    assert set(layer.fields) == {"id", "name", "place", "country", "reach_km", "secondary"}


def test_pack_json_says_postal_and_lists_the_countries_it_covers(built):
    path = built[0]
    about = json.loads((path / "pack.json").read_text())
    assert about["kind"] == "postal"
    assert about["covers"] == ["AU", "CZ", "DE", "FR", "GB"]
    assert "requires" not in about


@pytest.mark.parametrize(
    ("text", "ident"),
    [
        ("75007", "postal:FR:75007"),
        ("10117", "postal:DE:10117"),
        ("SW1A", "postal:GB:SW1A"),
        ("sw1a", "postal:GB:SW1A"),
        ("100 00", "postal:CZ:10000"),
        ("10000", "postal:CZ:10000"),
        ("2000", "postal:AU:2000"),  # the code's first point only
    ],
)
def test_the_name_index_finds_each_code_exactly(built, text, ident):
    pack = open_pack(built[0])
    found = pack.names.codes(text)
    layer = pack[const.LAYER]
    assert [layer.value("id", int(r)) for r in found.row] == [ident]


def test_place_names_are_not_search_names(built):
    pack = open_pack(built[0])
    assert not len(pack.names.exact("Paris 07")) and not len(pack.names.exact("The Rocks"))


def test_ids_are_derived_from_country_and_code_not_stored(built):
    path = built[0]
    spec = json.loads((path / const.LAYER / "layer.json").read_text())["fields"]["id"]
    assert spec["exceptions"] == 0 and "template" in spec
    assert not (path / const.LAYER / "col" / "id.npy").exists()
    layer = open_pack(path)[const.LAYER]
    assert layer.column("id").tolist() == [
        "postal:FR:75007", "postal:DE:10117", "postal:CZ:10000", "postal:GB:SW1A", "postal:AU:2000",
        "postal:AU:2000:2",
    ]  # fmt: skip
    assert open_pack(path).names.codes("postal:CZ:10000").row.tolist() == [2]  # found by its id
