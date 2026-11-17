"""Rename and label rules: changing the names an answer shows."""

import dataclasses

from placewise.model import Place, PlaceKind

from .state import in_area, merge, synthetic_id

# kind of the place a label rule creates when the answer has nothing in that field yet
_FIELD_KIND = {
    "city": PlaceKind.LOCALITY,
    "locality": PlaceKind.LOCALITY,
    "sublocality": PlaceKind.SUBLOCALITY,
    "borough": PlaceKind.BOROUGH,
    "admin1": PlaceKind.ADMIN1,
    "admin2": PlaceKind.ADMIN2,
}


def rename(state, entry, lat, lon):
    rule = entry.rule

    def renamed(place):
        if place.id != rule.id:
            return None
        old = (place.name,) if place.name != rule.name else ()
        return dataclasses.replace(
            place, name=rule.name, aliases=merge(place.aliases, old, rule.aliases)
        ), rule.origin

    if state.map_places(renamed):
        state.names_changed = rule.origin


def label(state, entry, lat, lon):
    rule = entry.rule
    if not in_area(rule.within, entry, state, lat, lon):
        return
    for name, value in sorted(rule.fields.items(), key=lambda kv: kv[0] == "label"):  # label text last
        if name == "label":
            state.fields["label"] = value
            state.label_set = True
            state.mark("label", rule.origin)
        elif name == "region":
            region = Place(synthetic_id(rule.origin, value, "region"), value, PlaceKind.REGION)
            state.fields["regions"] = [region, *(r for r in state.fields["regions"] if r.id != region.id)]
            state.mark("regions", rule.origin)
        else:
            current = state.fields[name]
            if current is None:
                state.fields[name] = Place(synthetic_id(rule.origin, value, name), value, _FIELD_KIND[name])
            elif current.name != value:
                aliases = merge(current.aliases, (current.name,))
                state.fields[name] = dataclasses.replace(current, name=value, aliases=aliases)
            else:
                continue
            state.mark(name, rule.origin)
            state.names_changed = rule.origin
