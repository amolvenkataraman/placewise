"""packbuild.aliases: datasets/names/aliases.json -> validation, the generated module, pack lookups."""

import json

import pytest
from datasets_kit import needs_datasets

from packbuild import aliases, cities
from packbuild.sources.geonames import GEONAME_FIELDS


def _entry(text, kind="short", **target):
    target = target or {"city": "Toronto", "country": "CA", "admin1": "ON", "geonames": 6167865}
    return {"text": text, "kind": kind, **target}


BLR = {"city": "Bengaluru", "country": "IN", "admin1": "KA", "geonames": 1277333}
SOURCE = {"title": "OurAirports", "url": "https://ourairports.com/airports/VOBL/"}


def _doc(*entries):
    return {"_comment": "test", "aliases": list(entries)}


def _write(tmp_path, *entries):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps(_doc(*entries)), encoding="utf-8")
    return path


# --- validation ---------------------------------------------------------------------------------


def test_load_reads_valid_entries(tmp_path):
    path = _write(
        tmp_path,
        _entry("TOR"),
        {**_entry("BLR", "code", **BLR), "reads_as": "city", "source": SOURCE},
        {"text": "Zaire", "kind": "former", "country": "CD", "until": "1997", "source": SOURCE},
        {"text": "Ernakulam", "kind": "suppress", "city": "Kochi", "country": "IN", "geonames": 1273874},
    )
    assert [e["text"] for e in aliases.load(path)] == ["TOR", "BLR", "Zaire", "Ernakulam"]


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({**_entry("TOR"), "kind": "nickname"}, "kind"),
        ({**_entry("TOR"), "colour": "red"}, "unknown fields"),
        ({"text": "TOR", "kind": "short", "country": "CA"}, "city"),  # only former names name a country
        ({**_entry("TOR"), "country": "XX"}, "country"),
        ({**_entry("TOR"), "admin1": "ZZ"}, "admin1"),
        ({**_entry("TOR"), "geonames": "6167865"}, "geonames"),
        (_entry("YYZ", "code"), "source"),  # a code cites its airport
        ({**_entry("Old Town", "former"), "until": "1998"}, "source"),  # a former name cites the rename
        ({**_entry("BLR", "code", **BLR), "source": SOURCE}, "reads_as"),  # BLR is also Belarus
        ({**_entry("KW"), "reads_as": "maybe"}, "reads_as"),
        ({**_entry("TOR"), "reads_as": "city"}, "reads_as"),  # not a code anything else uses
        ({**_entry("TOR"), "source": {"title": "x", "url": "http://example.com"}}, "https"),
    ],
)
def test_load_rejects_bad_entries(tmp_path, entry, message):
    with pytest.raises(ValueError, match=message):
        aliases.load(_write(tmp_path, entry))


def test_a_text_means_one_place(tmp_path):
    other = {"city": "Taranto", "country": "IT", "geonames": 3165926}
    with pytest.raises(ValueError, match="twice"):
        aliases.load(_write(tmp_path, _entry("TOR"), _entry("tor.", **other)))


def test_clash_codes_cover_iso_and_subdivision_codes():
    clashes = aliases.code_clashes
    assert clashes("BLR") and clashes("blr")  # Belarus
    assert clashes("SA") and clashes("LA") and clashes("ON") and clashes("ENG") and clashes("KA")
    assert not clashes("YYZ") and not clashes("Vegas") and not clashes("Austin")


def test_an_alias_may_share_a_region_name_only_for_the_city_the_region_is_named_after():
    regions = [
        {"id": "region:gta", "short_name": "GTA", "name": "Greater Toronto Area", "aliases": ["Toronto Area"],
         "country": "CA", "principal_cities": {"Toronto": "ON"}},
    ]  # fmt: skip
    aliases.check_regions([_entry("Toronto Area")], regions)  # Toronto is a principal city of the GTA
    with pytest.raises(ValueError, match="GTA"):
        aliases.check_regions(
            [_entry("GTA", city="Ottawa", country="CA", admin1="ON", geonames=6094817)], regions
        )


# --- GeoNames targets ---------------------------------------------------------------------------


def _row(gid, name, country, admin1, alternates=""):
    fields = dict.fromkeys(GEONAME_FIELDS, "")
    fields.update(
        geonameid=str(gid),
        name=name,
        asciiname=name,
        alternatenames=alternates,
        country_code=country,
        admin1_code=admin1,
        population="1000",
    )
    return "\t".join(fields[f] for f in GEONAME_FIELDS)


@pytest.fixture
def geonames(tmp_path):
    cities_path = tmp_path / "cities1000.txt"
    rows = [_row(6167865, "Toronto", "CA", "08"), _row(1277333, "Bengaluru", "IN", "19", "Bangalore")]
    cities_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    admin1 = tmp_path / "admin1CodesASCII.txt"
    admin1.write_text("CA.08\tOntario\tOntario\t6093943\nIN.19\tKarnataka\tKarnataka\t1267701\n")
    return cities_path, admin1


def test_check_targets_accepts_names_and_alternate_names(geonames):
    aliases.check_targets([_entry("TOR"), _entry("BLR-city", **{**BLR, "city": "Bangalore"})], *geonames)


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ({**BLR, "geonames": 1}, "no GeoNames city 1"),
        ({**BLR, "city": "Mysuru"}, "Mysuru"),
        ({**BLR, "country": "LK", "admin1": None}, "LK"),
        ({**BLR, "admin1": "TN"}, "TN"),
    ],
)
def test_check_targets_rejects_wrong_targets(geonames, target, message):
    with pytest.raises(ValueError, match=message):
        aliases.check_targets([_entry("X1", **target)], *geonames)


# --- outputs ------------------------------------------------------------------------------------


def test_render_writes_city_and_country_aliases():
    text = aliases.render(
        [
            _entry("TOR"),
            {**_entry("BLR", "code", **BLR), "reads_as": "city"},
            {**_entry("CAN", "code", city="Guangzhou", country="CN", geonames=1809858), "reads_as": "code"},
            {"text": "Zaire", "kind": "former", "country": "CD"},
            {"text": "Ernakulam", "kind": "suppress", "city": "Kochi", "country": "IN", "geonames": 1273874},
        ]
    )
    assert text.startswith('"""GENERATED from datasets/names/aliases.json by packbuild.cities; do not edit.')
    namespace = {}
    exec(compile(text, "city_aliases.py", "exec"), {"__name__": "placewise.constants.countries.x"}, namespace)
    found = namespace["CITY_ALIASES"]
    assert list(found) == ["TOR", "BLR", "CAN"]
    assert (found["TOR"].city, found["TOR"].admin1, found["TOR"].country, found["TOR"].kind) == (
        "Toronto",
        "ON",
        "CA",
        "short",
    )
    assert (found["BLR"].kind, found["BLR"].reads_as) == ("code", "city")
    assert (found["CAN"].admin1, found["CAN"].reads_as) == (None, "code")
    assert namespace["COUNTRY_ALIASES"] == {"Zaire": "CD"}


def test_pack_lookups_by_geonames_id():
    entries = [
        _entry("TOR"),
        _entry("YYZ", "code"),
        {**_entry("Old Toronto", "former"), "until": "1998"},
        {"text": "Ernakulam", "kind": "suppress", "city": "Kochi", "country": "IN", "geonames": 1273874},
        {**_entry("Bangalore", "former", **BLR)},
        {**_entry("Bengaluru", "name", **BLR)},
        {"text": "Zaire", "kind": "former", "country": "CD"},
    ]
    found = aliases.for_packs(entries)
    assert found.cities[6167865] == [
        ("Toronto", "name"),
        ("TOR", "short"),
        ("YYZ", "code"),
        ("Old Toronto", "former"),
    ]
    assert found.cities[1277333] == [("Bengaluru", "name"), ("Bangalore", "former")]
    assert found.suppressed == {1273874: {"ernakulam"}}
    assert found.countries == {"CD": [("Zaire", "former")]}


# --- the real dataset ---------------------------------------------------------------------------


@needs_datasets
def test_city_aliases_module_matches_the_dataset():
    path = cities.PACKAGE / "city_aliases.py"
    assert path.read_text(encoding="utf-8") == aliases.render(aliases.load()), (
        "constants/countries/city_aliases.py is out of date: run python -m packbuild.cities"
    )


@needs_datasets
def test_the_dataset_reads_every_large_airport_code_that_is_also_a_country_code():
    found = {e["text"]: e for e in aliases.load()}
    for code in ("AUS", "BLR", "CAN", "COK", "FRA", "IND", "MEX", "PER", "PHL", "HND", "MCO", "SYR"):
        assert found[code]["kind"] == "code" and found[code]["reads_as"] in aliases.READS_AS, code
    assert found["BLR"]["reads_as"] == "city" and found["CAN"]["reads_as"] == "code"
