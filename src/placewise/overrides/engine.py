"""The overrides engine: rules from the repo, the calling app and the user's own file, applied to answers.

Layers stack DATA < REPO < APP < LOCAL. `apply` runs the rules from the lowest layer to the highest
(file order within a layer), so a higher layer, or a later rule in the same layer, has the last
word. Tune rules are merged first (knob by knob, same precedence) and applied once at the end, so a
lower layer can't throw away entries that a higher layer's wider radius would keep.

Every field a rule changes is cited in `Result.sources[field]` as "override:<origin>", where origin
is "<layer>:<file>#<rule number>" ("repo:aliases.toml#1", "local:overrides.toml#3", "app#2"). Local
files are cited by file name only, so answers never carry the user's directory layout.
"""

import dataclasses

from placewise.model import Add, CityRule, Hide, Label, OverrideSet, RegionRule, Rename
from placewise.model.overrides import RULE_TYPES

from . import labels, names, places, regions
from .state import LIST_FIELDS, Entry, State, tag
from .tuning import apply_tuning, knobs

_TYPE_NAMES = {rule_type: name for name, rule_type in RULE_TYPES.items()}

# one handler per rule type
_HANDLERS = {
    Rename: labels.rename,
    Label: labels.label,
    CityRule: regions.city,
    RegionRule: regions.region,
    Hide: places.hide,
    Add: places.add,
    # Alias rules only affect forward search (resolve_name); Tune is merged in apply_tuning
}


class OverrideEngine:
    """Rules from every layer, in the order they apply. Build one with `load_overrides`."""

    __slots__ = ("_entries",)

    def __init__(self, sets=()):
        """`sets`: OverrideSets, or (OverrideSet, base_dir) pairs for rules read from a file."""
        entries = []
        for item in sets:
            override_set, base_dir = item if isinstance(item, tuple) else (item, None)
            entries.extend(Entry(rule, override_set.layer, base_dir) for rule in override_set.rules)
        entries.sort(key=lambda e: e.layer.precedence)  # stable: file and rule order survive
        self._entries = tuple(entries)

    @classmethod
    def from_documents(cls, documents):
        """From (layer, document, origin) or (layer, document, origin, base_dir) tuples."""
        sets = []
        for layer, doc, origin, *rest in documents:
            sets.append((OverrideSet.from_dict(layer, doc, origin), rest[0] if rest else None))
        return cls(sets)

    @property
    def rules(self):
        return tuple(e.rule for e in self._entries)

    def __len__(self):
        return len(self._entries)

    def __repr__(self):
        counts = {}
        for e in self._entries:
            counts[e.layer.value] = counts.get(e.layer.value, 0) + 1
        return f"OverrideEngine({counts})"

    # --- reverse lookups ------------------------------------------------------------------------

    def apply(self, result, lat, lon, relabel=None):
        """A new Result with every rule applied. `relabel(result) -> str`, if given, recomposes the
        label after a rule renamed something it shows (unless a label rule set the label text)."""
        state = State(result)
        for entry in self._entries:
            handler = _HANDLERS.get(type(entry.rule))
            if handler is not None:
                handler(state, entry, lat, lon)
        apply_tuning(self._entries, state)

        fields = dict(state.fields)
        for name in (*LIST_FIELDS, "near"):
            fields[name] = tuple(fields[name])
        out = dataclasses.replace(result, **fields, sources=state.sources)
        if relabel is not None and state.names_changed is not None and not state.label_set:
            label = relabel(out)
            if label != out.label:
                out = dataclasses.replace(
                    out, label=label, sources={**out.sources, "label": tag(state.names_changed)}
                )
        return out

    def tuning(self, place=None, *, id=None, kind=None):
        """Merged Tune knobs ({"tier", "near_km", "fame", "boost"}, only those set) for a place, or for
        rules targeting exactly an id or a kind. Higher layers and later rules win knob by knob."""
        return {knob: value for knob, (value, _) in knobs(self._entries, place, id, kind).items()}

    # --- forward search -------------------------------------------------------------------------

    def resolve_name(self, text, country=None, near=None):
        """Entity ids a name means by override, highest precedence first: alias rules, plus the
        names and aliases given by rename, region and add rules. `country` (ISO alpha-2) and
        `near` ((lat, lon)) skip aliases restricted to somewhere else. Ids hidden or removed by a
        rule are left out."""
        return names.resolve_name(self._entries, text, country, near)

    def explain(self):
        """Every rule, in the order it applies: [{"layer", "type", "origin", "rule"}]."""
        rows = []
        for entry in self._entries:
            rule = entry.rule.to_dict()
            rule.pop("origin", None)
            rows.append(
                {
                    "layer": entry.layer.value,
                    "type": _TYPE_NAMES[type(entry.rule)],
                    "origin": entry.rule.origin,
                    "rule": rule,
                }
            )
        return rows
