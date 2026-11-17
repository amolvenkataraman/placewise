"""Tune rules: knobs merged across layers (later and higher wins, knob by knob), applied once after
every other rule, so a lower layer can't throw away entries a higher layer's wider radius keeps."""

import dataclasses

from placewise.model import PlaceKind, Tune
from placewise.model.places import Relation

from .state import NEARBY_FIELDS

TUNE_KNOBS = ("tier", "near_km", "fame", "boost")


def knobs(entries, place, id_, kind):
    """{knob: (value, origin)} from the Tune rules that apply."""
    kind = PlaceKind(kind) if kind is not None else None

    def hit(rule):
        if place is not None:
            return rule.id == place.id if rule.id is not None else rule.kind == place.kind
        return (id_ is not None and rule.id == id_) or (kind is not None and rule.kind == kind)

    out = {}
    for entry in entries:
        if isinstance(entry.rule, Tune) and hit(entry.rule):
            for knob in TUNE_KNOBS:
                if (value := getattr(entry.rule, knob)) is not None:
                    out[knob] = (value, entry.rule.origin)
    return out


class Tunes:
    """The Tune rules, indexed by the id and the kind they target."""

    def __init__(self, entries):
        self.entries = tuple(e for e in entries if isinstance(e.rule, Tune))
        self._by_id, self._by_kind = {}, {}
        for i, entry in enumerate(self.entries):
            rule = entry.rule
            if rule.id is not None:
                self._by_id.setdefault(rule.id, []).append(i)
            elif (kind := _kind(rule.kind)) is not None:
                self._by_kind.setdefault(kind, []).append(i)

    def knobs(self, place):
        """knobs(entries, place, None, None), from just the rules aimed at this place."""
        hits = (*self._by_id.get(place.id, ()), *self._by_kind.get(place.kind, ()))
        out = {}
        for i in sorted(hits):
            rule = self.entries[i].rule
            for knob in TUNE_KNOBS:
                if (value := getattr(rule, knob)) is not None:
                    out[knob] = (value, rule.origin)
        return out

    def apply(self, state):
        """Retier places and drop near entries beyond their near_km, citing the rule that did it."""
        if self.entries:
            apply_tuning(state, self.knobs)


def _kind(kind):
    """The PlaceKind a rule's kind equals, or None (then it matches no place)."""
    try:
        return PlaceKind(kind)
    except ValueError:
        return None


def apply_tuning(state, knobs_for):
    """Retier places and drop near entries beyond their near_km; `knobs_for(place)` gives a place's
    merged knobs."""

    def retier(place):
        tier = knobs_for(place).get("tier")
        if tier is None or place.tier == tier[0]:
            return None
        return dataclasses.replace(place, tier=tier[0]), tier[1]

    state.map_places(retier)

    def too_far(nearby):
        limit = knobs_for(nearby.place).get("near_km")
        if nearby.relation is Relation.NEAR and limit is not None and nearby.distance_km > limit[0]:
            return limit[1]
        return None

    kept = []
    for nearby in state.fields["near"]:
        if (origin := too_far(nearby)) is not None:
            state.mark("near", origin)
        else:
            kept.append(nearby)
    state.fields["near"] = kept
    for name in NEARBY_FIELDS:
        if (nearby := state.fields[name]) is not None and (origin := too_far(nearby)) is not None:
            state.fields[name] = None
            state.mark(name, origin)
