"""Reference tables: ISO 3166-1 countries, US states, Canadian provinces, Indian states, UK nations."""

import json
from pathlib import Path

import pytest

from placewise.constants import countries
from placewise.constants.countries import can, conventions, currency_codes, gbr, ind, usa
from placewise.constants.location_text import CURRENCY_CITY_HINTS

us_states = usa.subregions
ca_provinces = can.subregions
in_states = ind.subregions

ISO_CODES = Path("/usr/share/iso-codes/json/iso_3166-1.json")  # Debian's mirror of ISO 3166-1


# --- US states (USPS Publication 28, Census FIPS) -------------------------------------------------


def test_us_has_fifty_states_dc_and_five_inhabited_territories():
    kinds = [s.kind for s in us_states.STATES]
    assert kinds.count("state") == 50
    assert kinds.count("district") == 1
    assert kinds.count("territory") == 5
    assert {s.usps for s in us_states.STATES if s.kind == "territory"} == {"AS", "GU", "MP", "PR", "VI"}


@pytest.mark.parametrize(
    ("usps", "name", "fips"),
    [
        ("AL", "Alabama", "01"),
        ("AK", "Alaska", "02"),
        ("AZ", "Arizona", "04"),
        ("CA", "California", "06"),
        ("DC", "District of Columbia", "11"),
        ("GA", "Georgia", "13"),
        ("NY", "New York", "36"),
        ("RI", "Rhode Island", "44"),
        ("WA", "Washington", "53"),
        ("WY", "Wyoming", "56"),
        ("AS", "American Samoa", "60"),
        ("GU", "Guam", "66"),
        ("MP", "Northern Mariana Islands", "69"),
        ("PR", "Puerto Rico", "72"),
        ("VI", "U.S. Virgin Islands", "78"),
    ],
)
def test_us_codes(usps, name, fips):
    state = us_states.BY_CODE[usps]
    assert (state.name, state.fips) == (name, fips)


def test_us_codes_and_fips_are_unique():
    assert len({s.usps for s in us_states.STATES}) == len(us_states.STATES)
    assert len({s.fips for s in us_states.STATES}) == len(us_states.STATES)
    # FIPS skips the numbers once reserved for territories: 03, 07, 14, 43, 52
    assert not {"03", "07", "14", "43", "52"} & {s.fips for s in us_states.STATES}


@pytest.mark.parametrize(
    ("text", "usps"),
    [("calif", "CA"), ("Calif.", "CA"), ("N.Y.", "NY"), ("n mex", "NM"), ("W. Va.", "WV"), ("Wash.", "WA")],
)
def test_us_traditional_abbreviations(text, usps):
    assert us_states.lookup(text) == usps


# --- Canadian provinces (Statistics Canada SGC) ---------------------------------------------------


def test_canada_has_ten_provinces_and_three_territories():
    kinds = [p.kind for p in ca_provinces.PROVINCES]
    assert kinds.count("province") == 10 and kinds.count("territory") == 3


@pytest.mark.parametrize(
    ("code", "name", "sgc"),
    [
        ("NL", "Newfoundland and Labrador", "10"),
        ("QC", "Quebec", "24"),
        ("ON", "Ontario", "35"),
        ("BC", "British Columbia", "59"),
        ("NU", "Nunavut", "62"),
    ],
)
def test_canada_codes(code, name, sgc):
    province = ca_provinces.BY_CODE[code]
    assert (province.name, province.sgc) == (name, sgc)


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("Ont.", "ON"),
        ("Que", "QC"),
        ("Québec", "QC"),
        ("Colombie-Britannique", "BC"),
        ("P.E.I.", "PE"),
        ("Nouvelle-Écosse", "NS"),
        ("N.W.T.", "NT"),
        ("Alta.", "AB"),
    ],
)
def test_canada_aliases_are_input_only(text, code):
    assert ca_provinces.lookup(text) == code
    # names stay English
    assert all(p.name.isascii() for p in ca_provinces.PROVINCES)


# --- Indian states and union territories (ISO 3166-2:IN) ------------------------------------------


def test_india_has_28_states_and_8_union_territories():
    kinds = [s.kind for s in in_states.STATES]
    assert kinds.count("state") == 28 and kinds.count("union_territory") == 8


@pytest.mark.parametrize(
    ("code", "name"),
    [
        ("KA", "Karnataka"),
        ("MH", "Maharashtra"),
        ("DL", "Delhi"),
        ("TN", "Tamil Nadu"),
        ("TS", "Telangana"),
        ("OD", "Odisha"),
        ("CG", "Chhattisgarh"),
        ("UK", "Uttarakhand"),
        ("LA", "Ladakh"),
        ("DH", "Dadra and Nagar Haveli and Daman and Diu"),
    ],
)
def test_india_current_iso_codes(code, name):
    assert in_states.BY_CODE[code].name == name


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("TG", "TS"),
        ("OR", "OD"),
        ("CT", "CG"),
        ("UT", "UK"),
        ("Orissa", "OD"),
        ("Bangalore", None),
        ("NCT of Delhi", "DL"),
        ("Pondicherry", "PY"),
        ("J&K", "JK"),
        ("Uttaranchal", "UK"),
    ],
)
def test_india_former_codes_and_names(text, code):
    assert in_states.lookup(text) == code


# --- Countries (ISO 3166-1) -----------------------------------------------------------------------


def test_every_iso_3166_1_country():
    assert len(countries.COUNTRIES) == 249
    assert len({c.alpha3 for c in countries.COUNTRIES}) == 249
    assert len({c.numeric for c in countries.COUNTRIES}) == 249


@pytest.mark.skipif(not ISO_CODES.exists(), reason="Debian iso-codes not installed")
def test_codes_match_the_iso_codes_package():
    iso = json.loads(ISO_CODES.read_text())["3166-1"]
    expected = {(e["alpha_2"], e["alpha_3"], e["numeric"]) for e in iso}
    assert {(c.alpha2, c.alpha3, c.numeric) for c in countries.COUNTRIES} == expected


@pytest.mark.parametrize(
    ("text", "iso2"),
    [
        ("USA", "US"),
        ("U.S.", "US"),
        ("u.s.a.", "US"),
        ("America", "US"),
        ("United States of America", "US"),
        ("UK", "GB"),
        ("Britain", "GB"),
        ("Great Britain", "GB"),
        ("UAE", "AE"),
        ("Holland", "NL"),
        ("South Korea", "KR"),
        ("Korea, Republic of", "KR"),
        ("Turkey", "TR"),
        ("Côte d'Ivoire", "CI"),
        ("cote d'ivoire", "CI"),
        ("Trinidad & Tobago", "TT"),
        ("CAN", "CA"),
        ("IND", "IN"),
        ("Canada", "CA"),
    ],
)
def test_country_lookup(text, iso2):
    assert countries.lookup(text) == iso2


def test_country_names_are_english_short_names():
    assert countries.BY_ALPHA2["US"].name == "United States"
    assert countries.BY_ALPHA2["KR"].name == "South Korea"
    assert countries.BY_ALPHA2["GE"].name == "Georgia"
    assert countries.BY_ALPHA2["CA"].alpha3 == "CAN"
    assert countries.lookup("Atlantis") is None


# --- Layout and country-level details -------------------------------------------------------------


def test_every_subregion_has_an_iso_3166_2_code():
    for alpha2, table in countries.SUBREGIONS.items():
        for sub in table.SUBREGIONS:
            assert sub.iso == f"{alpha2}-{sub.code}"
    assert us_states.BY_CODE["NY"].usps == "NY"


def test_gb_nations():
    assert [n.iso for n in gbr.subregions.SUBREGIONS] == ["GB-ENG", "GB-SCT", "GB-WLS", "GB-NIR"]
    assert gbr.subregions.lookup("England") == "ENG"
    assert countries.lookup("England") is None  # a subdivision of GB, not a country alias


@pytest.mark.parametrize(
    ("module", "alpha2", "alpha3", "currency"),
    [
        (usa.country, "US", "USA", "USD"),
        (can.country, "CA", "CAN", "CAD"),
        (ind.country, "IN", "IND", "INR"),
        (gbr.country, "GB", "GBR", "GBP"),
    ],
)
def test_country_modules(module, alpha2, alpha3, currency):
    assert (module.ALPHA2, module.ALPHA3) == (alpha2, alpha3) and not hasattr(module, "CURRENCY")
    assert module.NAME == countries.BY_ALPHA2[alpha2].name
    assert currency_codes.CURRENCY_CODES[alpha2] == currency  # the one country -> currency table


@pytest.mark.parametrize(
    ("module", "good", "bad"),
    [
        (usa.country, ["94103", "94103-1234"], ["9410"]),
        (can.country, ["M5V 2T6", "K1A0B1"], ["D5V 2T6", "M5V 2T"]),
        (ind.country, ["560001", "110 001"], ["060001"]),
        (gbr.country, ["SW1A 1AA", "EC1V 9BD"], ["SW1A"]),
    ],
)
def test_postal_code_formats(module, good, bad):
    for code in good:
        assert module.POSTAL_CODE.fullmatch(code), code
    for code in bad:
        assert not module.POSTAL_CODE.fullmatch(code), code


def test_currency_codes_and_any_case_alpha3_use_real_codes():
    codes = currency_codes.CURRENCY_CODES
    assert set(codes) <= set(countries.BY_ALPHA2) and len(codes) == 248  # all but Antarctica
    assert all(len(c) == 3 and c.isupper() and c.isalpha() for c in codes.values())
    assert (codes["BG"], codes["SV"], codes["IN"]) == ("EUR", "USD", "INR")
    assert set(CURRENCY_CITY_HINTS.values()) <= set(codes.values())
    assert conventions.ALPHA3_ANY_CASE <= set(countries.BY_ALPHA3)
    assert conventions.STATE_CODES_ALSO_COUNTRIES <= set(countries.BY_ALPHA2)
