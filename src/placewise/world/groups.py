"""Country groups (constants.countries.groups): lookups, lists, and memberships over time."""

import functools

from placewise.constants._keys import key
from placewise.constants.countries import groups as table
from placewise.model import CountryGroup, Membership

from . import _resolve
from .countries import country as _country


def _legal(gid, data):
    members, others = [], []
    for m in data["members"]:
        if m["code"] is None:
            others.append(m.get("group") or m.get("entity"))
        else:
            members.append(Membership(m["code"], m["since"], m["until"], m.get("suspended_since")))
    return CountryGroup(
        gid,
        data["name"],
        data["aliases"],
        data["kind"],
        "legal",
        members,
        data["source"],
        data["notes"],
        others,
    )


@functools.cache
def _all():
    found = {
        gid: CountryGroup(
            gid,
            data["name"],
            data["aliases"],
            data["kind"],
            "geographic",
            tuple(Membership(code) for code in data["members"]),
            data["source"],
            data["notes"],
        )
        for gid, data in table.GEOGRAPHIC.items()
    }
    found.update((gid, _legal(gid, data)) for gid, data in table.LEGAL.items())
    return found


@functools.cache
def _by_name():
    return {key(n): g.id for g in _all().values() for n in (g.name, *g.aliases)}


def _kinds():
    return sorted({g.kind for g in _all().values()})


def group(x):
    """The group an id ("legal:eu"), name or alias ("EU", "US & Canada", "Western Europe") means,
    in any case. KeyError names the input and close matches."""
    if isinstance(x, CountryGroup):
        return x
    found = _all().get(str(x).strip()) or _all().get(_by_name().get(key(str(x)), ""))
    if found is None:
        raise _resolve.not_found(
            "country group", x, [n for g in _all().values() for n in (g.name, *g.aliases)]
        )
    return found


def codes(g, on):
    """The alpha-2 codes of a group's members on `on` (YYYY-MM-DD); geographic groups are undated."""
    return {m.country for m in g.members if _resolve.active(m, on)}


def groups(of=None, kind=None, category=None, as_of=None):
    """Every group, sorted by name, narrowed to those `of` (a country, by any code or name) belongs
    to on `as_of` (default today), of a `kind` and of a `category` ("geographic" or "legal")."""
    if category is not None and category not in ("geographic", "legal"):
        raise ValueError(f"category {category!r} must be 'geographic' or 'legal'")
    if kind is not None and kind not in _kinds():
        raise ValueError(f"kind {kind!r} is not one of {', '.join(_kinds())}")
    on = _resolve.day(as_of)
    alpha2 = _country(of).alpha2 if of is not None else None
    found = [
        g
        for g in _all().values()
        if (kind is None or g.kind == kind)
        and (category is None or g.category == category)
        and (alpha2 is None or alpha2 in codes(g, on))
    ]
    return sorted(found, key=lambda g: g.name)


def members(g, as_of=None):
    """The countries in a group on `as_of` (default today), sorted by name."""
    from .countries import countries

    return countries(group=group(g).id, as_of=as_of)


def is_member(country, g, on=None):
    """Was `country` in group `g` on `on` (default today)?"""
    return _country(country).alpha2 in codes(group(g), _resolve.day(on))
