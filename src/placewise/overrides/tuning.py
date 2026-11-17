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


def apply_tuning(entries, state):
    """Retier places and drop near entries beyond their near_km, citing the rule that did it."""
    if not any(isinstance(e.rule, Tune) for e in entries):
        return

    def retier(place):
        tier = knobs(entries, place, None, None).get("tier")
        if tier is None or place.tier == tier[0]:
            return None
        return dataclasses.replace(place, tier=tier[0]), tier[1]

    state.map_places(retier)

    def too_far(nearby):
        limit = knobs(entries, nearby.place, None, None).get("near_km")
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
