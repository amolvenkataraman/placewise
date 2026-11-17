"""Countries: one by code or name, and lists filtered by group, continent, group kind and date."""

import functools

from placewise.constants import countries as table
from placewise.model import Country

from . import _resolve


@functools.cache
def _official_names():
    """alpha-2 -> official name, from the per-country modules that give one (usa, can, ind, gbr)."""
    modules = (table.usa.country, table.can.country, table.ind.country, table.gbr.country)
    return {m.ALPHA2: m.OFFICIAL_NAME for m in modules}


@functools.cache
def _all():
    official = _official_names()
    return {
        c.alpha2: Country(c.alpha2, c.alpha3, c.numeric, c.name, official.get(c.alpha2), c.aliases)
        for c in table.COUNTRIES
    }


def country(x):
    """The country an ISO 3166-1 alpha-2, alpha-3 or numeric code, name or alias means, in any
    case: "CA", "can", "124", 124, "Canada", "U.S.". KeyError names the input and close matches."""
    text = f"{x:03d}" if isinstance(x, int) and not isinstance(x, bool) else str(x).strip()
    if text.isdigit():
        found = table.BY_NUMERIC.get(text.zfill(3))
        alpha2 = found.alpha2 if found else None
    else:
        alpha2 = table.lookup(text)
    if alpha2 is None:
        raise _resolve.not_found("country", x, [n for c in table.COUNTRIES for n in (c.name, *c.aliases)])
    return _all()[alpha2]


def countries(group=None, continent=None, kind=None, as_of=None):
    """Every country, sorted by name, narrowed by each filter given:

    - group: a group id, name or alias ("EU", "EMEA", "US & Canada", "CANZUK"), or a list of them
      meaning the countries in all of them;
    - continent: a continent ("Europe", "oceania"), as constants.countries.groups assigns them;
    - kind: a group kind ("union", "alliance", "currency-union" ...): countries in any group of it;
    - as_of: the date memberships are taken on (a date or "YYYY-MM-DD"; default today).
    """
    from .groups import codes as _codes
    from .groups import group as _group
    from .groups import groups as _groups

    on = _resolve.day(as_of)
    codes = set(_all())
    names = [group] if isinstance(group, str) else list(group or ())
    for name in names:
        codes &= _codes(_group(name), on)
    if continent is not None:
        found = _group(continent)
        if found.kind != "continent":
            continents = ", ".join(g.name for g in _groups(kind="continent"))
            raise KeyError(f"{continent!r} is not a continent (continents: {continents})")
        codes &= _codes(found, on)
    if kind is not None:
        codes &= set().union(*(_codes(g, on) for g in _groups(kind=kind)))
    return sorted((_all()[c] for c in codes), key=lambda c: c.name)
