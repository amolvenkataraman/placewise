"""packbuild.country_profiles: GeoNames, CLDR and Wikidata files -> the world pack's country_facts layer."""

import math

import pytest
from facts_kit import DATA, fake_fetch

from packbuild import country_profiles as cp
from packbuild.fetch import DEFAULT_CACHE
from placewise.packs import open_pack, write_pack


@pytest.fixture(scope="module")
def built():
    return cp.build(cp.inputs("unused-cache", fetcher=fake_fetch))


def test_build_joins_the_sources(built):
    assert set(built) == set(cp._countries())  # every ISO 3166-1 code, with or without facts
    ca = built["CA"]
    assert (ca["name"], ca["iso3"], ca["capital"], ca["continent"]) == (
        "Canada",
        "CAN",
        "Ottawa",
        "North America",
    )
    assert (ca["currency"], ca["currency_name"], ca["currency_symbol"], ca["currency_narrow_symbol"]) == (
        "CAD",
        "Canadian Dollar",
        "CA$",
        "$",
    )
    assert ca["calling_code"] == "+1" and ca["languages"] == ("en-CA", "fr-CA", "iu")
    assert ca["time_zones"] == ("America/Toronto", "America/Vancouver") and ca["neighbours"] == ("US",)
    assert (ca["measurement_system"], ca["first_day_of_week"]) == ("metric", "sunday")
    assert (ca["locale"], ca["date_format"], ca["driving_side"]) == ("en-CA", "y-MM-dd", "right")
    assert ca["population"] > 30_000_000 and ca["population_year"] is None
    india = built["IN"]
    assert (india["currency"], india["locale"], india["date_format"]) == ("INR", "hi", "d/M/yy")
    us = built["US"]
    assert us["measurement_system"] == "US" and us["currency"] == "USD"  # USN is not legal tender
    assert us["driving_side"] is None  # the Wikidata rows disagree: left out
    assert built["GB"]["measurement_system"] == "imperial-mixed"  # CLDR "UK"
    assert built["SV"]["currency"] == "USD"  # SVC ended in 2001
    aq = built["AQ"]
    assert aq["currency"] is None and aq["locale"] is None and aq["capital"] is None  # "XXX", "und"
    assert built["FR"]["first_day_of_week"] == "monday"  # CLDR's world default (001)


def test_calling_codes_and_numbers():
    assert cp._phone("1") == "+1" and cp._phone("+1-268") == "+1-268"
    assert cp._phone("+1-809 and 1-829") == "+1-809, +1-829" and cp._phone("") is None
    assert cp._number("468") == 468 and cp._number("0.44") == 0.44 and cp._number("") is None


def test_capitals_pick_the_pplc_city():
    from packbuild.sources.geonames import read_country_facts

    points = cp.capitals(DATA / "cities.txt", read_country_facts(DATA / "countryInfo.txt"))
    assert set(points) == {"CA"} and points["CA"] == pytest.approx((45.41117, -75.69812), abs=1e-3)


def test_layer_writes_and_reads_back(built, tmp_path):
    layer = cp.layer(built, {"CA": (45.4, -75.7)}, label_points={"AQ": (-80.0, 0.0)})
    assert layer.columns["id"] == ["iso:AQ", "iso:CA"] and layer.columns["point"] == ["label", "capital"]
    assert "naturalearth" in layer.sources
    pack = open_pack(write_pack(tmp_path, "world", "2026.11", [layer], created="2026-11-17T00:00:00Z"))
    facts = pack["country_facts"]
    row = facts.row(int(facts.find("id", "iso:CA")[0]))
    assert row["languages"] == "en-CA,fr-CA,iu" and row["time_zones"] == "America/Toronto,America/Vancouver"
    assert row["population_year"] is None and row["population"] > 0
    aq = facts.row(int(facts.find("id", "iso:AQ")[0]))
    assert aq["currency"] is None and aq["calling_code"] is None
    assert facts.fields["population"] == "i8" and facts.fields["area_km2"] == "f8"


def test_countries_without_a_point_are_left_out(built):
    layer = cp.layer(built, {"CA": (45.4, -75.7)})
    assert layer.columns["id"] == ["iso:CA"] and layer.sources == ("geonames", "cldr", "wikidata")
    assert not any(isinstance(v, float) and math.isnan(v) for v in layer.columns["population"])


def test_locale_rules():
    available = {"zh", "zh-Hant", "zh-Hant-HK", "sr-Latn", "sr", "en", "en-CA", "ms"}
    likely = {
        "zh": "zh-Hans-CN",
        "sr": "sr-Cyrl-RS",
        "ms": "ms-Latn-MY",
        "en": "en-Latn-US",
        "und": "en-Latn-US",
    }
    assert cp.cldr.locale_for("zh-Hant-TW", available, likely) == "zh-Hant"
    assert cp.cldr.locale_for("zh-Hant-HK", available, likely) == "zh-Hant-HK"
    assert cp.cldr.locale_for("sr-Cyrl-RS", available, likely) == "sr"  # Cyrillic is Serbian's default
    assert cp.cldr.locale_for("ms-Arab-BN", available, likely) is None  # "ms" is Latin script
    # no "und-XX": CLDR's default language with that region, only where CLDR has that locale
    assert cp.cldr.territory_locale("CA", likely, available) == "en-CA"
    assert cp.cldr.territory_locale("US", likely, available) == "en"
    assert cp.cldr.territory_locale("HM", likely, available) is None


@pytest.mark.skipif(not cp.cached(DEFAULT_CACHE), reason="country facts sources not downloaded")
def test_the_real_sources_cover_every_country():
    built = cp.build(cp.inputs(DEFAULT_CACHE, offline=True))
    assert built["CA"]["currency"] == "CAD" and built["GB"]["driving_side"] == "left"
    assert sum(1 for f in built.values() if f["currency"]) >= 248
