"""Country groups that limit remote work ("Remote - EMEA"), read from the country-group tables
(constants.countries.groups); which groups count is constants.location_text.REMOTE_SCOPE_GROUPS."""

import datetime as dt
import functools
from dataclasses import dataclass

from placewise.constants._keys import key
from placewise.constants.countries import groups
from placewise.constants.location_text import REMOTE_SCOPE_GROUPS, WORLDWIDE_GROUP


@dataclass(frozen=True)
class ScopeRegion:
    """A group as a remote-work limit; `members` None means no limit (worldwide)."""

    id: str
    name: str
    aliases: tuple[str, ...]
    members: frozenset[str] | None

    def contains(self, country):
        return self.members is None or country in self.members


def _current(member, today):
    """Is a legal group's member a member today? Year-only dates cover the whole year."""
    since, until = member["since"], member["until"]
    return (since is None or since <= today) and (until is None or f"{until}-12-31"[:10] >= today)


def _region(gid, today):
    group = groups.GEOGRAPHIC.get(gid) or groups.LEGAL[gid]
    if gid == WORLDWIDE_GROUP:
        members = None
    elif gid in groups.GEOGRAPHIC:
        members = frozenset(group["members"])
    else:
        members = frozenset(m["code"] for m in group["members"] if m["code"] and _current(m, today))
    return ScopeRegion(gid, group["name"], tuple(group["aliases"]), members)


@functools.cache
def all_regions():
    """Every scope region, memberships as of today."""
    today = dt.date.today().isoformat()
    return tuple(_region(gid, today) for gid in REMOTE_SCOPE_GROUPS)


@functools.cache
def _index():
    return {key(alias): region for region in all_regions() for alias in (region.name, *region.aliases)}


def find(text):
    """The scope region a name means ("EMEA", "Asia Pacific", "Worldwide"), or None."""
    return _index().get(key(text)) if text else None
