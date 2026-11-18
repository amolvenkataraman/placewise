"""Finding metros and city aliases (data: constants.countries.regions and .city_aliases)."""

import dataclasses
import functools

from placewise.constants._keys import city_key as key
from placewise.constants.countries import CITY_ALIASES, METROS, CityAlias
from placewise.constants.countries.city_aliases import COUNTRY_ALIASES

__all__ = [
    "all_metros",
    "any_alias",
    "city_alias",
    "country_alias",
    "find",
    "is_member_city",
    "key",
    "metro_of",
    "metros_naming",
]


@functools.cache
def _index():
    by_name, by_city_alias, by_city = {}, {}, {}
    for metro in METROS:
        for name in (metro.key, metro.name, *metro.aliases):
            by_name[key(name)] = metro
        for alias, city in metro.city_aliases.items():
            by_city_alias[key(alias)] = CityAlias(city, metro.admin1_of(city), metro.country, metro)
        for city, code in metro.cities.items():
            by_city[(key(city), metro.country, code)] = metro
    for alias, entry in CITY_ALIASES.items():
        metro = entry.metro or by_city.get((key(entry.city), entry.country, entry.admin1))
        by_city_alias[key(alias)] = dataclasses.replace(entry, metro=metro) if metro else entry
    naming = {}  # city key -> metros listing a city of that name, in by_city order
    for (name, _, _), metro in by_city.items():
        naming.setdefault(name, []).append(metro)
    return {m.key: m for m in METROS}, by_name, by_city_alias, by_city, naming


@functools.cache
def _country_aliases():
    return {key(alias): code for alias, code in COUNTRY_ALIASES.items()}


def by_id():
    """Every metro, keyed by its short id (shared: don't modify)."""
    return _index()[0]


def all_metros():
    """Every metro, keyed by its short id."""
    return dict(_index()[0])


def find(text):
    """The metro a name or alias means ("Greater Toronto Area", "gtha", "S.F. Bay Area"), or None."""
    return _index()[1].get(key(text)) if text else None


def city_alias(text):
    """The CityAlias for another name of a city ("NYC", "Bangalore", "SF", "PDX"), or None. Codes
    that keep their own meaning alone ("CAN" is Canada, not Guangzhou's airport) are left out."""
    alias = any_alias(text)
    return alias if alias is not None and alias.reads_as != "code" else None


def any_alias(text):
    """The CityAlias for any other name of a city, codes that keep their own meaning included
    ("CAN" -> Guangzhou), or None: for telling a code written next to its own city."""
    return _index()[2].get(key(text)) if text else None


def country_alias(text):
    """The alpha-2 code of a country's former name ("Zaire" -> "CD"), or None."""
    return _country_aliases().get(key(text)) if text else None


def metro_of(city, country, admin1):
    """The metro listing this city in this country and admin1, or None."""
    if not city or not country or not admin1:
        return None
    return _index()[3].get((key(city), country, admin1))


def metros_naming(city):
    """Metros listing a city of this name in any admin1 (for matching a city given without one)."""
    return list(_index()[4].get(key(city), ()))


def is_member_city(text):
    """Is this a city some metro lists (so noise words like "Greater" in it are part of the name)?"""
    return key(text) in _index()[4]
