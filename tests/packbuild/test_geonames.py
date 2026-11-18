from pathlib import Path

import pytest

from packbuild.sources import geonames

DATA = Path(__file__).parent / "data"


@pytest.fixture
def layer():
    return geonames.cities(DATA / "cities.txt", DATA / "admin1CodesASCII.txt", DATA / "countryInfo.txt")


def test_cities_is_a_point_layer_with_geonames_ids(layer):
    assert layer.name == "cities" and layer.kind == "point" and layer.sources == ("geonames",)
    assert list(layer.columns["id"]) == [
        "geonames:6167865",
        "geonames:6094817",
        "geonames:1277333",
        "geonames:5511077",
        "geonames:7262586",
    ]
    assert list(layer.columns["name"])[:3] == ["Toronto", "Ottawa", "Bengaluru"]
    assert list(layer.lat)[2] == pytest.approx(12.97194) and list(layer.lon)[2] == pytest.approx(77.59369)
    assert layer.features is None


def test_columns(layer):
    c = {k: list(v) for k, v in layer.columns.items()}
    assert c["asciiname"][4] == "Yosemite Valley"
    assert c["country"] == ["CA", "CA", "IN", "US", "US"]
    assert c["admin1"] == ["08", "08", "19", "NV", "CA"]
    assert c["feature_code"] == ["PPLA", "PPLC", "PPLA", "PPLA2", "PPL"]
    assert c["population"] == [2794356, 1017449, 8495492, 264165, 1035]
    assert (
        c["timezone"] == ["America/Toronto", "America/Toronto", "Asia/Kolkata"] + ["America/Los_Angeles"] * 2
    )
    assert c["alternate_count"] == [3, 2, 4, 1, 0]
    assert "alternatenames" not in c  # the full list is too big for the world pack
    assert layer.types["population"] == "i8"
    assert layer.types["timezone"] == "str"


def test_admin1_name_is_joined_and_missing_codes_stay_empty(layer):
    # Yosemite Valley's admin1 (US.CA) is absent from the fixture's admin1CodesASCII.txt
    assert list(layer.columns["admin1_name"]) == ["Ontario", "Ontario", "Karnataka", "Nevada", ""]


def test_elevation_falls_back_to_the_dem_and_no_data_is_null(layer):
    # Toronto and Ottawa have no surveyed elevation, so the DEM's is used; -9999 is "no data"
    null = layer.nulls["elevation"]
    assert list(layer.columns["elevation"]) == [92, 71, 920, 1373, null]
    assert layer.types["elevation"] == "i2" and null == -32768


def test_parsing_is_tabs_only_and_keeps_quotes(tmp_path):
    row = ["1", 'Fort "Old" Town', "Fort Old Town, x", "", "1.5", "2.5", "P", "PPL", "XX"] + [""] * 10
    path = tmp_path / "c.txt"
    path.write_text("\t".join(row) + "\r\n", encoding="utf-8")
    [parsed] = list(geonames.read_tsv(path, 19))
    assert parsed[1] == 'Fort "Old" Town' and parsed[2] == "Fort Old Town, x"


def test_a_short_row_is_an_error(tmp_path):
    path = tmp_path / "c.txt"
    path.write_text("1\tA\tA\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        list(geonames.read_tsv(path, 19))


def test_country_info_skips_comments():
    assert geonames.read_country_info(DATA / "countryInfo.txt") == {
        "CA": "Canada",
        "IN": "India",
        "US": "United States",
    }


def test_unknown_country_codes_are_reported(tmp_path, caplog):
    info = tmp_path / "countryInfo.txt"
    info.write_text("CA\tCAN\t124\tCA\tCanada\n", encoding="utf-8")
    geonames.cities(DATA / "cities.txt", DATA / "admin1CodesASCII.txt", info)
    assert "not in countryInfo" in caplog.text and "IN" in caplog.text


# --- alternateNamesV2 ---------------------------------------------------------------------------

ALTERNATES = [
    # id, geonameid, language, name, preferred, short, colloquial, historic, from, to
    ("1", "1277333", "en", "Bengaluru", "1", "", "", "", "", ""),
    ("2", "1277333", "en", "Bangalore", "", "", "", "1", "", ""),
    ("3", "1277333", "iata", "BLR", "", "", "", "", "", ""),
    ("4", "1277333", "fr", "Bangalore", "1", "", "", "", "", ""),
    ("5", "1277333", "", "Bangalore City", "", "", "", "", "", ""),
    ("6", "1277333", "link", "https://en.wikipedia.org/wiki/Bengaluru", "", "", "", "", "", ""),
    ("7", "5368361", "en", "LA", "", "1", "1", "", "", ""),
    ("8", "5368361", "en", "Big Apple", "", "", "1", "", "", ""),
    ("9", "5368361", "abbr", "L.A.", "", "", "", "", "", ""),
    ("10", "5368361", "en", "Ciudad|Angeles", "", "", "", "", "", ""),
    ("11", "5368361", "en", "Los‌Angeles", "", "", "", "", "", ""),
    ("12", "9999999", "en", "Nowhere", "", "", "", "", "", ""),
]


@pytest.fixture
def alternates_zip(tmp_path):
    import zipfile

    path = tmp_path / "alternateNamesV2.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("alternateNamesV2.txt", "".join("\t".join(r) + "\n" for r in ALTERNATES))
        z.writestr("iso-languagecodes.txt", "ignored\n")
    return path


def test_read_alternate_names_streams_only_the_wanted_features(alternates_zip):
    found = geonames.read_alternate_names(alternates_zip, {1277333, 5368361})
    assert set(found) == {1277333, 5368361}
    assert [(a.language, a.name, a.historic) for a in found[1277333]][:3] == [
        ("en", "Bengaluru", False),
        ("en", "Bangalore", True),
        ("iata", "BLR", False),
    ]
    assert all(a.language != "link" for names in found.values() for a in names)


def test_pick_alternates_keeps_english_codes_and_curated_former_names(alternates_zip):
    found = geonames.read_alternate_names(alternates_zip, {1277333, 5368361})
    big = geonames.pick_alternates(found[1277333], population=8_000_000, formers={"bangalore"})
    assert big == [("BLR", "code"), ("Bengaluru", "name"), ("Bangalore", "former")]
    # a historic name nobody curated, or a small place's, is left out; so are other languages
    assert geonames.pick_alternates(found[1277333], population=8_000_000) == [
        ("BLR", "code"),
        ("Bengaluru", "name"),
    ]
    assert ("Bangalore", "former") not in geonames.pick_alternates(
        found[1277333], population=50_000, formers={"bangalore"}
    )
    # short names even when colloquial; other nicknames, '|' and invisible characters are dropped
    assert geonames.pick_alternates(found[5368361], population=3_800_000) == [
        ("L.A.", "abbr"),
        ("LA", "short"),
    ]
    assert geonames.pick_alternates(found[1277333], codes=False, population=1) == [("Bengaluru", "name")]
