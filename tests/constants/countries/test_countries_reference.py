"""Curated and generated reference data: regions, city aliases, generated cities and ambiguous names."""

import pytest

from placewise.constants import countries
from placewise.constants._keys import city_key
from placewise.constants.countries import ambiguous

ADMIN1 = {alpha2: set(table.BY_CODE) for alpha2, table in countries.SUBREGIONS.items()}


def _admin1_ok(country, code):
    known = ADMIN1.get(country)
    return code is None or known is None or code in known


def test_regions_are_well_formed():
    assert countries.METROS
    ids = [m.id for m in countries.METROS]
    assert len(ids) == len(set(ids)) and all(i.startswith("region:") for i in ids)
    for metro in countries.METROS:
        assert metro.country in countries.BY_ALPHA2, metro.key
        assert all(_admin1_ok(metro.country, code) for code in metro.admin1), metro.key
        assert all(code in metro.admin1 for code in metro.cities.values()), metro.key
        assert all(city in metro.cities for city in metro.city_aliases.values()), metro.key


def test_region_ids_the_overrides_use_are_kept():
    ids = {m.id for m in countries.METROS}
    assert {"region:gta", "region:sf-bay-area"} <= ids


def test_region_and_city_alias_names_are_unique():
    seen = {}
    for metro in countries.METROS:
        for name in (metro.key, metro.name, *metro.aliases, *metro.city_aliases):
            assert seen.setdefault(city_key(name), metro.key) == metro.key, name
    for alias in countries.CITY_ALIASES:
        assert seen.setdefault(city_key(alias), "city_aliases") == "city_aliases", alias


def test_city_aliases_use_known_codes():
    for alias, entry in countries.CITY_ALIASES.items():
        assert entry.country in countries.BY_ALPHA2, alias
        assert _admin1_ok(entry.country, entry.admin1), alias


def test_generated_cities_use_known_admin1():
    for country, rows in countries.CITIES.items():
        assert rows, country
        for name, admin1, population in rows:
            assert admin1 in ADMIN1[country], (country, name)
            assert population >= 0
    names = {name for name, _, _ in countries.CITIES["CA"]}
    assert {"Toronto", "Ottawa", "Mississauga"} <= names


def test_ambiguous_cities_use_known_codes():
    for city, candidates in ambiguous.AMBIGUOUS_CITIES.items():
        assert len(candidates) >= 2, city
        assert sum(c.weight for c in candidates) == pytest.approx(1.0), city
        for c in candidates:
            assert c.country in countries.BY_ALPHA2 and _admin1_ok(c.country, c.admin1), city
    for name, clash in ambiguous.NAME_CLASHES.items():
        assert clash.country in countries.BY_ALPHA2 and _admin1_ok(clash.admin1_country, clash.admin1), name
