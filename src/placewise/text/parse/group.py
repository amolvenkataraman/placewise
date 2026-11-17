"""Parts into places: a city, then its admin1 and country; several places in one list."""

import itertools
from dataclasses import dataclass, field

from .readings import _Reading
from .tokenize import _display, _Token


@dataclass
class _Group:
    city: _Token | None = None
    metro: _Token | None = None
    regions: list = field(default_factory=list)
    junk: list = field(default_factory=list)
    remote: bool = False

    @property
    def tokens(self):
        return [t for t in (self.city, self.metro, *self.regions) if t]

    @property
    def span(self):
        tokens = self.tokens or self.junk
        return (min(t.start for t in tokens), max(t.end for t in tokens))


def _consistent(token_readings, allow_india):
    """Combinations of one reading per token that agree on a country and an admin1."""
    combos = []
    for combo in itertools.product(*token_readings):
        if len({r.country for r in combo}) != 1:
            continue
        if len({r.admin1 for r in combo if r.admin1}) > 1:
            continue
        if any(r.india_code for r in combo) and not (
            allow_india or any(r.country == "IN" and not r.india_code for r in combo)
        ):
            continue
        combos.append(combo)
    return combos


def _joins_metro(group, tok):
    """Does a metro named after a place belong to it? "Toronto, GTA", "Ontario, GTA", and
    "Washington, D.C. Metro Area", where the region name turns out to be the city."""
    metro = tok.metro
    if group.city is not None:
        if group.city.kind not in ("city", "alias"):
            return False
        own = [[_Reading(metro.country)], *[t.readings for t in group.regions]]
        return not group.regions or bool(_consistent(own, True))
    if len(group.regions) != 1:
        return False
    first = group.regions[0]
    same = [r for r in first.readings if r.country == metro.country and not r.india_code]
    if any(r.admin1 is None or r.admin1 in metro.admin1 for r in same):
        return True
    if same and any(r.by_name for r in first.readings):
        first.kind, first.text = "city", _display(first.text)
        group.city, group.regions = first, []
        return True
    return False


def _group(tokens):
    """Tokens -> places: a city, then its admin1 and country; a new city or a region that can't
    belong starts the next place."""
    groups, current = [], None

    def new():
        nonlocal current
        current = _Group()
        groups.append(current)

    for tok in tokens:
        if tok.kind == "junk":
            if current is None:
                new()
            current.junk.append(tok)
            continue
        if tok.kind == "metro" and current is not None and not current.metro and _joins_metro(current, tok):
            current.metro = tok
            continue
        if tok.kind in ("city", "alias", "metro", "macro"):
            if current is None or current.city or current.metro or current.regions:
                new()
            if tok.kind == "metro":
                current.metro = tok
            else:
                current.city = tok
            continue
        if current is None:
            new()
        elif current.regions:
            first = current.regions[0]
            # "Ontario, CA", "Washington, DC": a region name before a state or province is a city
            if (
                not current.city
                and not current.metro
                and len(current.regions) == 1
                and any(r.by_name and r.admin1 for r in first.readings)
                and any(r.admin1 and not r.india_code for r in tok.readings)
            ):
                first.kind, first.text = "city", _display(first.text)
                current.city, current.regions = first, [tok]
                continue
            if not _consistent([t.readings for t in [*current.regions, tok]], True):
                new()
        current.regions.append(tok)
    return [g for g in groups if g.tokens or g.junk]
