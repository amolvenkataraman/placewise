"""Known cities (generated from GeoNames: constants.countries.<alpha3>.cities) and metro member
cities (constants.countries.regions), for telling which reading of a code a named city fits."""

import functools

from placewise.constants._keys import city_key as key
from placewise.constants.countries import CITIES, METROS


@functools.cache
def _index():
    """city key -> {(country, admin1)}"""
    index = {}
    for country, rows in CITIES.items():
        for name, admin1, _ in rows:
            index.setdefault(key(name), set()).add((country, admin1))
    for metro in METROS:
        for name, admin1 in metro.cities.items():
            index.setdefault(key(name), set()).add((metro.country, admin1))
    return index


def is_known(city, country, admin1):
    """Is there a known city of this name in this country and admin1?"""
    return bool(city) and (country, admin1) in _index().get(key(city), ())


def admin1s(city, country):
    """The admin1 codes of known cities of this name in this country."""
    return {a for c, a in _index().get(key(city), ()) if c == country} if city else set()
