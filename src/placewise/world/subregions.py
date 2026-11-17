"""ISO 3166-2 subdivisions of the countries with tables (constants.countries.<alpha3>.subregions)."""

import functools
import re

from placewise.constants._keys import key
from placewise.constants.countries import SUBREGIONS as TABLES
from placewise.model import Subregion

from . import _resolve
from .countries import country as _country

_ISO_3166_2 = re.compile(r"([A-Za-z]{2})-([A-Za-z0-9]{1,3})")
_EXTRA_CODES = ("fips", "sgc")  # other code systems a table carries


def _model(alpha2, row):
    codes = {name: getattr(row, name) for name in _EXTRA_CODES if hasattr(row, name)}
    kind = row.kind.replace("_", " ")  # "union_territory" -> "union territory"
    return Subregion(f"{alpha2}-{row.code}", row.code, row.name, kind, alpha2, row.aliases, codes)


@functools.cache
def _all(alpha2):
    return tuple(_model(alpha2, row) for row in TABLES[alpha2].SUBREGIONS)


def _table(country):
    c = _country(country)
    if c.alpha2 not in TABLES:
        have = ", ".join(_country(a).name for a in TABLES)
        raise LookupError(
            f"subdivisions of {c.name} ({c.alpha2}) are not available yet; placewise has them for {have}"
        )
    return c.alpha2


def subregions(country, kind=None):
    """The subdivisions of a country (any code or name), in table order, optionally of one kind
    ("state", "province", "territory", "union territory" ...). Countries without a table raise
    LookupError rather than return an empty list."""
    found = _all(_table(country))
    if kind is not None:
        kinds = sorted({s.kind for s in found})
        if kind not in kinds:
            raise ValueError(f"kind {kind!r}: {found[0].country} subdivisions are {', '.join(kinds)}")
        found = tuple(s for s in found if s.kind == kind)
    return list(found)


@functools.cache
def _by_short_code(alpha2):
    out = {}
    for s in _all(alpha2):
        out.setdefault(s.short_code, s)
    return out


@functools.cache
def _name_keys():
    """Normalised names and aliases of every subdivision in every table."""
    return frozenset(key(n) for a in TABLES for s in _all(a) for n in (s.name, *s.aliases))


def _in(alpha2, text):
    short = TABLES[alpha2].lookup(text)
    return _by_short_code(alpha2).get(short) if short else None


def subregion(x, country=None):
    """The subdivision "CA-ON", "Ontario", "Ont." or ("ON", country="CA") means. Without a country
    every table is searched; a name or code several countries share is a KeyError listing them."""
    text = str(x).strip()
    if country is not None:
        alpha2 = _table(country)
        prefixed = _ISO_3166_2.fullmatch(text)
        if prefixed and prefixed.group(1).upper() == alpha2:
            text = prefixed.group(2)
        found = _in(alpha2, text)
        if found is None:
            raise _resolve.not_found(
                f"subdivision of {alpha2}", x, [n for s in _all(alpha2) for n in (s.name, *s.aliases)]
            )
        return found
    prefixed = _ISO_3166_2.fullmatch(text)
    if prefixed and key(text) not in _name_keys():
        return subregion(prefixed.group(2), country=prefixed.group(1).upper())
    matches = [s for alpha2 in TABLES if (s := _in(alpha2, text)) is not None]
    if len(matches) > 1:
        raise KeyError(f"{x!r} is ambiguous: {', '.join(s.code for s in matches)}; pass country=")
    if not matches:
        names = [n for a in TABLES for s in _all(a) for n in (s.name, *s.aliases)]
        raise _resolve.not_found("subdivision", x, names)
    return matches[0]
