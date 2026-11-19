"""Tier crosswalks and the name and id rules of the park sources (packbuild.sources.parks.tiers)."""

import pytest

from packbuild.sources.parks import tiers
from placewise.constants.parks import LOCAL, NATIONAL, REGIONAL, STATE, TIERS


def test_every_crosswalk_names_a_known_tier():
    assert {t for t, _ in tiers.NPS_TYPES.values()} <= set(TIERS)
    assert {t for t, _ in tiers.PADUS_TYPES.values()} <= set(TIERS)
    assert set(tiers.CPCAD_TYPES.values()) <= set(TIERS)
    assert set(tiers.WIKIDATA_CLASSES.values()) <= set(TIERS)


def test_flagships_are_national_and_city_parks_local():
    assert tiers.NPS_TYPES["National Parks"] == (NATIONAL, "National Park")
    assert tiers.CPCAD_TYPES["National Urban Park"] == NATIONAL  # Rouge
    assert tiers.CPCAD_TYPES["Provincial Park"] == STATE and tiers.PADUS_TYPES["SP"][0] == STATE
    assert tiers.CPCAD_TYPES["Conservation Reserve"] == REGIONAL
    assert tiers.PADUS_TYPES["LP"] == (LOCAL, "Local Park")
    # private, NGO and habitat designations aren't parks
    for dropped in (
        "Privately Protected Area",
        "Water fowl gathering area",
        "White-tailed deer yard",
        "OECM",
    ):
        assert dropped not in tiers.CPCAD_TYPES
    assert "PCON" not in tiers.PADUS_TYPES and "TRIBL" not in tiers.PADUS_TYPES


@pytest.mark.parametrize(
    ("name", "usable"),
    [("Central Park", True), ("Yosemite National Park", True), ("", False), ("Unknown", False),
     ("BLM 123", False), ("Tax#0313-05-2531", False), ("City of Newport", False), ("Town Forest", True)],
)  # fmt: skip
def test_usable_names(name, usable):
    assert tiers.usable_name(name) is usable


@pytest.mark.parametrize(
    ("name", "generic"),
    [("Open Space", True), ("open  SPACE", True), ("Unknown Park", True), ("Park", True),
     ("Conservation Easement", True), ("Natural Area", True), ("Municipal Open Space", True),
     ("Heron Ridge Open Space", False), ("Central Park", False), ("City Park", False),
     ("Yosemite National Park", False), ("", False)],
)  # fmt: skip
def test_generic_names(name, generic):
    assert tiers.generic_name(name) is generic


def test_cpcad_names_lose_their_suffixes():
    assert tiers.cpcad_name("Banff National Park Of Canada") == (
        "Banff National Park", "Banff National Park of Canada"
    )  # fmt: skip
    assert tiers.cpcad_name("Algonquin Provincial Park (Natural Environment Class)") == (
        "Algonquin Provincial Park", ""
    )  # fmt: skip
    assert tiers.cpcad_name("  Rouge National   Urban Park ") == ("Rouge National Urban Park", "")


def test_short_names_slugs_and_name_tiers():
    assert tiers.short_name("Yosemite National Park", "National Park") == "Yosemite"
    assert tiers.short_name("National Park", "National Park") == ""
    assert tiers.short_name("Central Park", "Local Park") == ""
    assert tiers.slug("Parc national du Mont-Mégantic") == "parc-national-du-mont-megantic"
    assert tiers.name_tier("Kaziranga National Park") == NATIONAL
    assert tiers.name_tier("Corbett Tiger Reserve") == NATIONAL
    assert tiers.name_tier("Bhimashankar Wildlife Sanctuary") == STATE
    assert tiers.name_tier("Sundarbans") is None


@pytest.mark.parametrize(
    ("category", "english", "iucn", "km2", "expected"),
    [
        ("A", "National Park", "II", 300.0, (NATIONAL, "National Park")),
        ("A", "Nacional Park", "II", 300.0, (NATIONAL, "National Park")),  # ES08, as the EEA spells it
        ("A", "National Park - Core Area", "II", 900.0, (NATIONAL, "National Park")),  # FR01
        ("A", "Swiss National Park", "Ia", 170.0, (NATIONAL, "National Park")),
        ("A", "National Park (category II)", "II", 100.0, (NATIONAL, "National Park")),
        ("C", "National Park", "notApplicable", 50.0, (NATIONAL, "National Park")),  # NL22: still one
        ("A", "National Park - Buffer zone/Area of adhesion", "V", 1500.0, None),  # whole towns: FR16
        ("A", "National Park - Peripheral zone", "V", 500.0, None),
        ("C", "National Park to be established", "V", 50.0, None),
        ("A", "Strict nature reserve of national park", "Ia", 10.0, (REGIONAL, "Strict nature reserve of national park")),  # noqa: E501
        ("A", "Regional Nature Park", "V", 1000.0, (STATE, "Nature Park")),  # tier 2: a few kinds
        ("A", "Regional/Provincial Nature Park", "V", 30.0, (STATE, "Nature Park")),
        ("A", "Landscape Park", "V", 30.0, (STATE, "Landscape Park")),
        ("A", "Protected Landscape Area", "V", 30.0, (STATE, "Protected Landscape Area")),
        ("A", "Naturpark", "V", 30.0, (STATE, "Nature Park")),
        ("A", "biosphere reserve", "V", 300.0, (STATE, "Biosphere Reserve")),
        ("A", "Nature park IIIb (FBiH law)", "V", 30.0, (STATE, "Nature Park")),
        ("A", "Managed Nature Reserve (category IV IUCN)", "IV", 3.0, (REGIONAL, "Managed Nature Reserve")),
        ("A", "Nature Reserve (Svalbard)", "IV", 3.0, (REGIONAL, "Nature Reserve")),
        ("A", "special conservation areas", "IV", 3.0, (REGIONAL, "Special Conservation Areas")),
        ("A", "biosphere reserve - transition area", "V", 300.0, None),
        ("A", "Nature Reserve", "IV", 2.0, (REGIONAL, "Nature Reserve")),
        ("A", "Nature Reserve", "IV", 0.5, None),  # too small to name from afar
        ("A", "Strict Nature Reserve", "II", 150.0, (STATE, "Strict Nature Reserve")),  # IUCN II, large
        ("A", "Strict Nature Reserve", "II", 20.0, (REGIONAL, "Strict Nature Reserve")),
        ("A", "Landscape Protection Area", "V", 500.0, None),  # Landschaftsschutzgebiet: everywhere
        ("A", "Natura 2000 SCI", "notApplicable", 50.0, None),
        ("A", "Ramsar Sites", "notApplicable", 50.0, None),
        ("A", "No Protection Status", "notApplicable", 50.0, None),
        ("B", "Forest Reserves", "IV", 50.0, None),  # sectoral
        ("C", "Private Nature Reserve", "IV", 50.0, None),
        ("A", "Biotope Protection Order", "IV", 50.0, None),
    ],
)  # fmt: skip
def test_eea_designation_types(category, english, iucn, km2, expected):
    assert tiers.eea_tier(category, english, iucn, km2) == expected


def test_eea_code_overrides():
    # Poland's and Latvia's "protected landscape areas" are light designations over farmland and towns
    assert tiers.eea_tier("A", "Protected Landscape Area", "V", 500.0, code="PL04")[0] == REGIONAL
    assert tiers.eea_tier("A", "Protected Landscape Area", "V", 500.0, code="CZ09")[0] == STATE
    denmark = "Protected by conservation order, excl. Church surroundings"
    assert tiers.eea_tier("A", denmark, "IV", 3.0, code="DK01") == (REGIONAL, denmark)
    assert tiers.eea_tier("A", "Biotope Protection Order", "IV", 3.0, code="FR05") is None


@pytest.mark.parametrize(
    ("raw", "clean"),
    [("2001221 Sarek", "Sarek"), ("Gaujas Nacionālais parks NZ 3822", "Gaujas Nacionālais parks"),
     ("P N DELLE DOLOMITI BELLUNESI", "P N Delle Dolomiti Bellunesi"),
     ("  Plitvička   jezera ", "Plitvička jezera"),
     ("Ecrins", "Ecrins"), ("12345", "")],
)  # fmt: skip
def test_eea_names(raw, clean):
    assert tiers.eea_name(raw) == clean


def test_eea_nature_parks_are_never_labels():
    # nature parks, biosphere reserves and protected landscapes take in whole towns, like national forests
    from placewise.constants.parks import LABEL_SKIP_DESIGNATIONS

    assert set(tiers.EEA_STATE_DESIGNATIONS) <= LABEL_SKIP_DESIGNATIONS
