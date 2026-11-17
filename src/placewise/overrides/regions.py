"""City and region rules: the display city, and which regions a point belongs to."""

import dataclasses

from placewise.model import AreaSelector, Place, PlaceKind

from .state import PLACE_FIELDS, in_area, merge, synthetic_id


def city(state, entry, lat, lon):
    rule = entry.rule
    if rule.within is not None:
        hit = in_area(rule.within, entry, state, lat, lon)
    else:
        locality = state.fields["locality"]
        hit = locality is not None and locality.id == rule.locality
    if not hit:
        return
    current = state.fields["city"]
    if current is not None and current.name == rule.city:
        return
    kind = current.kind if current is not None else PlaceKind.LOCALITY
    state.fields["city"] = Place(synthetic_id(rule.origin, rule.city), rule.city, kind)
    state.mark("city", rule.origin)
    state.names_changed = rule.origin


def region(state, entry, lat, lon):
    rule = entry.rule
    regions = state.fields["regions"]
    at = next((i for i, r in enumerate(regions) if r.id == rule.id), None)
    member = not rule.remove and _region_member(rule, entry, state, lat, lon)
    if not member:
        if at is not None:
            del regions[at]
            state.mark("regions", rule.origin)
        return
    current = regions[at] if at is not None else None
    if current is None:
        place = Place(rule.id, rule.label or rule.id, PlaceKind.REGION, aliases=rule.aliases)
        regions.append(place)
    else:
        place = dataclasses.replace(
            current, name=rule.label or current.name, aliases=merge(current.aliases, rule.aliases)
        )
        if place == current:
            return
        regions[at] = place
    state.mark("regions", rule.origin)


def _region_member(rule, entry, state, lat, lon):
    places = [p for name in PLACE_FIELDS if (p := state.fields[name]) is not None]
    for key, codes in rule.members.items():
        for place in places:
            value = place.id if key == "id" else place.codes.get(key)
            if value is not None and value in codes:
                return True
    if rule.polygon is not None:
        return in_area(AreaSelector(geojson=rule.polygon), entry, state, lat, lon)
    return False
