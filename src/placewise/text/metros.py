"""Finding metros and city aliases (data: constants.countries.<cc>.metros and .cities)."""

import functools

from placewise.constants._keys import city_key as key
from placewise.constants.countries import CITY_ALIASES, METROS, CityAlias

__all__ = ["all_metros", "city_alias", "find", "is_member_city", "key", "metro_of", "metros_naming"]


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
        by_city_alias[key(alias)] = entry
    return {m.key: m for m in METROS}, by_name, by_city_alias, by_city


def all_metros():
    """Every metro, keyed by its short id."""
    return dict(_index()[0])


def find(text):
    """The metro a name or alias means ("Greater Toronto Area", "gtha", "S.F. Bay Area"), or None."""
    return _index()[1].get(key(text)) if text else None


def city_alias(text):
    """The CityAlias for another name of a city ("NYC", "Bangalore", "SF", "PDX"), or None."""
    return _index()[2].get(key(text)) if text else None


def metro_of(city, country, admin1):
    """The metro listing this city in this country and admin1, or None."""
    if not city or not country or not admin1:
        return None
    return _index()[3].get((key(city), country, admin1))


def metros_naming(city):
    """Metros listing a city of this name in any admin1 (for matching a city given without one)."""
    k = key(city)
    return [metro for (name, _, _), metro in _index()[3].items() if name == k]


def is_member_city(text):
    """Is this a city some metro lists (so noise words like "Greater" in it are part of the name)?"""
    k = key(text)
    return any(name == k for name, _, _ in _index()[3])
