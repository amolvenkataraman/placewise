"""Hide and add rules: taking places out of an answer and putting new ones in."""

from placewise.geo.distances import haversine
from placewise.model import Nearby, Place, PlaceKind
from placewise.model.places import Relation

from .state import LIST_FIELDS, NEARBY_FIELDS, in_area, synthetic_id


def hide(state, entry, lat, lon):
    rule = entry.rule
    for name in LIST_FIELDS:
        kept = [p for p in state.fields[name] if p.id != rule.id]
        if len(kept) != len(state.fields[name]):
            state.fields[name] = kept
            state.mark(name, rule.origin)
    kept = [n for n in state.fields["near"] if n.place.id != rule.id]
    if len(kept) != len(state.fields["near"]):
        state.fields["near"] = kept
        state.mark("near", rule.origin)
    for name in NEARBY_FIELDS:
        if (n := state.fields[name]) is not None and n.place.id == rule.id:
            state.fields[name] = None
            state.mark(name, rule.origin)


def add(state, entry, lat, lon):
    rule = entry.rule
    distance = float(haversine(rule.point.lat, rule.point.lon, lat, lon))
    if rule.within is not None:
        hit = in_area(rule.within, entry, state, lat, lon)
    else:
        hit = distance <= rule.radius_m / 1000.0
    if not hit:
        return
    place = Place(rule.id or synthetic_id(rule.origin, rule.name), rule.name, rule.kind, point=rule.point)
    if rule.kind is PlaceKind.AIRPORT:
        state.fields["airport"] = Nearby(place, Relation.AT, distance)
        field = "airport"
    elif rule.kind is PlaceKind.WATER:
        state.fields["water"] = Nearby(place, Relation.ON, distance)  # OVER: engine._water.in_flight
        field = "water"
    else:
        field = "regions" if rule.kind is PlaceKind.REGION else "within"
        state.fields[field] = [place, *(p for p in state.fields[field] if p.id != place.id)]
    state.mark(field, rule.origin)
    near = [n for n in state.fields["near"] if n.place.id != place.id]  # it's here now, not near
    if len(near) != len(state.fields["near"]):
        state.fields["near"] = near
        state.mark("near", rule.origin)
