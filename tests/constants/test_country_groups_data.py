"""The generated country-group tables: spot checks against the published memberships."""

import pytest

from placewise.constants.countries import BY_ALPHA2
from placewise.constants.countries import groups as g


def current(gid):
    """Alpha-2 codes of a legal group's current country members."""
    return {m["code"] for m in g.LEGAL[gid]["members"] if m["code"] and m["until"] is None}


def former(gid):
    return {m["code"]: m["until"] for m in g.LEGAL[gid]["members"] if m["until"] is not None}


def test_as_of_is_a_date():
    assert len(g.AS_OF) == 10 and g.AS_OF[4] == "-" and g.AS_OF[7] == "-"


# --- US & Canada: one group that is exactly the two countries ---

US_CANADA_ALIASES = (
    "US & Canada",
    "US and Canada",
    "USA & Canada",
    "USA and Canada",
    "US/Canada",
    "U.S. & Canada",
    "Canada & US",
    "Canada and the US",
    "North America (US & Canada)",
)


def test_us_and_canada_is_exactly_us_and_canada():
    group = g.GEOGRAPHIC["geo:us-canada"]
    assert group["name"] == "US & Canada" and group["kind"] == "custom"
    assert set(group["members"]) == {"US", "CA"} and len(group["members"]) == 2


@pytest.mark.parametrize("alias", US_CANADA_ALIASES)
def test_us_and_canada_aliases_resolve_to_it(alias):
    assert g.ALIASES[alias.lower()] == "geo:us-canada"


def test_north_america_is_the_continent_not_us_and_canada():
    assert g.ALIASES["north america"] == "geo:north-america"
    assert {"US", "CA", "MX", "PA", "JM"} <= set(g.GEOGRAPHIC["geo:north-america"]["members"])
    assert set(g.GEOGRAPHIC["geo:northern-america"]["members"]) == {"BM", "CA", "GL", "PM", "US"}


# --- legal memberships ---


def test_eu_has_27_members_and_the_uk_left_on_31_january_2020():
    assert len(current("legal:eu")) == 27
    assert former("legal:eu") == {"GB": "2020-01-31"}


def test_eurozone_matches_the_ecb_count():
    # ECB, "Members of the European Union using the euro": 21 countries since Bulgaria joined on 2026-01-01
    zone = current("legal:eurozone")
    assert len(zone) == 21 and "BG" in zone and zone <= current("legal:eu")


def test_schengen_includes_its_non_eu_members():
    schengen = current("legal:schengen")
    assert {"CH", "NO", "IS", "LI"} <= schengen
    assert len(schengen) == 29 and not {"IE", "CY"} & schengen


def test_eea_is_the_eu_plus_iceland_liechtenstein_and_norway():
    assert current("legal:eea") == current("legal:eu") | {"IS", "LI", "NO"}


def test_canzuk():
    assert current("legal:canzuk") == {"CA", "AU", "NZ", "GB"}


def test_five_eyes():
    assert current("legal:five-eyes") == {"US", "GB", "CA", "AU", "NZ"}


def test_cusma():
    assert current("legal:cusma") == {"US", "CA", "MX"}


def test_g20_has_the_eu_and_african_union_as_non_country_members():
    members = g.LEGAL["legal:g20"]["members"]
    assert len(current("legal:g20")) == 19
    assert {m["group"] for m in members if m["code"] is None} == {"legal:eu", "legal:african-union"}


@pytest.mark.parametrize(
    ("gid", "count"),
    [
        ("legal:nato", 32),
        ("legal:oecd", 38),
        ("legal:asean", 11),
        ("legal:gcc", 6),
        ("legal:commonwealth", 56),
        ("legal:g7", 7),
        ("legal:efta", 4),
        ("legal:cptpp", 12),
    ],
)
def test_member_counts(gid, count):
    assert len(current(gid)) == count


def test_african_union_has_55_members():
    assert len(g.LEGAL["legal:african-union"]["members"]) == 55


def test_mercosur_records_venezuela_as_suspended():
    venezuela = next(m for m in g.LEGAL["legal:mercosur"]["members"] if m["code"] == "VE")
    assert venezuela["until"] is None and venezuela["suspended_since"]


# --- integrity ---


def test_every_member_code_is_iso_alpha2():
    codes = {c for group in g.GEOGRAPHIC.values() for c in group["members"]}
    codes |= {m["code"] for group in g.LEGAL.values() for m in group["members"] if m["code"]}
    assert codes <= set(BY_ALPHA2)


def test_aliases_are_unique_and_all_resolve():
    seen = {}
    for gid, group in (*g.GEOGRAPHIC.items(), *g.LEGAL.items()):
        for alias in (group["name"], *group["aliases"]):
            key = alias.lower()
            assert seen.setdefault(key, gid) == gid, f"{alias!r} in {gid} and {seen[key]}"
            assert g.ALIASES[key] == gid
    assert set(seen) == set(g.ALIASES)


@pytest.mark.parametrize("alias", ["EU", "EMEA", "APAC", "US & Canada", "LATAM", "Schengen", "Nordics"])
def test_aliases_location_search_will_need(alias):
    assert alias.lower() in g.ALIASES


def test_ids_are_prefixed_by_file():
    assert all(gid.startswith("geo:") for gid in g.GEOGRAPHIC)
    assert all(gid.startswith("legal:") for gid in g.LEGAL)
