"""What the rule handlers share: the answer being rewritten, the rule entries, and small helpers for
citing rules and building places."""

import dataclasses
from pathlib import Path

from placewise.constants import overrides as const
from placewise.model import Layer

PLACE_FIELDS = ("country", "admin1", "admin2", "city", "locality", "sublocality", "borough")
LIST_FIELDS = ("regions", "within")
NEARBY_FIELDS = ("airport", "water")


@dataclasses.dataclass(frozen=True, slots=True)
class Entry:
    rule: object
    layer: Layer
    base_dir: Path | None  # relative GeoJSON paths in the rule resolve against this


class State:
    """The answer being rewritten: mutable copies of the fields rules touch."""

    __slots__ = ("fields", "label_set", "names_changed", "sources")

    def __init__(self, result):
        self.fields = {name: getattr(result, name) for name in ("label", *PLACE_FIELDS, *NEARBY_FIELDS)}
        for name in (*LIST_FIELDS, "near"):
            self.fields[name] = list(getattr(result, name))
        self.sources = dict(result.sources)
        self.label_set = False  # a label rule set the label text itself
        self.names_changed = None  # origin of the last rule that changed a name

    def mark(self, field, origin):
        self.sources[field] = tag(origin)

    @property
    def cc(self):
        country = self.fields["country"]
        return country.codes.get("iso2") if country else None

    @property
    def place_ids(self):
        ids = {p.id for name in PLACE_FIELDS if (p := self.fields[name]) is not None}
        ids.update(p.id for name in LIST_FIELDS for p in self.fields[name])
        return ids

    def map_places(self, fn):
        """Replace places everywhere they appear. fn(place) -> (new place, origin) or None.
        Returns the origins used, so callers can tell whether anything changed."""
        used = []

        def swap(place, field):
            out = fn(place)
            if out is None or out[0] == place:
                return place
            self.mark(field, out[1])
            used.append(out[1])
            return out[0]

        for name in PLACE_FIELDS:
            if self.fields[name] is not None:
                self.fields[name] = swap(self.fields[name], name)
        for name in LIST_FIELDS:
            self.fields[name] = [swap(p, name) for p in self.fields[name]]
        self.fields["near"] = [with_place(n, swap(n.place, "near")) for n in self.fields["near"]]
        for name in NEARBY_FIELDS:
            if (n := self.fields[name]) is not None:
                self.fields[name] = with_place(n, swap(n.place, name))
        return used


# --- helpers ------------------------------------------------------------------------------------


def in_area(area, entry, state, lat, lon):
    return area.matches(lat, lon, cc=state.cc, place_ids=state.place_ids, base_dir=entry.base_dir)


def tag(origin):
    return f"{const.SOURCE_PREFIX}:{origin}" if origin else const.SOURCE_PREFIX


def synthetic_id(origin, name, field=None):
    """Id for a place a rule creates: cites the rule, so apps grouping by id can trace it."""
    base = origin or "-".join(name.casefold().split())
    return f"{const.SOURCE_PREFIX}:{base}" + (f"/{field}" if field else "")


def merge(*groups):
    out = []
    for group in groups:
        out.extend(name for name in group if name not in out)
    return tuple(out)


def with_place(nearby, place):
    return nearby if place is nearby.place else dataclasses.replace(nearby, place=place)
