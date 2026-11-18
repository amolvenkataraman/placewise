"""Result.matches: for each place field, whether the point is inside the place or the place is a
fallback chosen by distance or score, and how far (docs/naming.md, "How each name was found").

Read off the rule each field's source names ("usa/places:polygon", "world/cities:score"):
constants.lookup.MATCH_WITHIN_RULES put the point inside the place (distance 0); "offshore" is a
country or state whose territorial sea holds it; every other rule (nearest, score, metro, postal,
inside ...) is a fallback, `near` at the great-circle km to the place's point. A polygon taken
across a shore gap (rule "nearest") and a place known only by its outline are measured to their
bounding box, which within the shore margin is the distance to the polygon; None where the box
holds the point but the outline doesn't, so the distance isn't known. Fields an override set
("override:...") have none.
"""

import math

from placewise.constants import lookup as const
from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.overrides import SOURCE_PREFIX
from placewise.model import Match, Relation

FIELDS = ("country", "admin1", "admin2", "city", "locality", "sublocality", "borough", "postal")
WITHIN = Match(Relation.WITHIN, 0.0)  # shared: Matches are frozen


def matches(fields, sources, lat, lon):
    """{field: Match} for the place fields of one Result (`fields` a dict of them)."""
    out = {}
    for name in FIELDS:
        place = fields.get(name)
        if place is None:
            continue
        kind = _KINDS.get(sources.get(name))
        if kind is None:
            kind = _kind(sources.get(name))
        if kind is _SKIP:
            continue
        if kind is WITHIN:
            out[name] = WITHIN
        else:
            relation, rule = kind
            out[name] = Match(relation, _distance(place, rule, lat, lon))
    return out


_SKIP = object()
_KINDS = {}  # source text -> WITHIN, _SKIP or (relation, rule); sources are a few dozen strings


def _kind(source):
    if source is None or source.startswith(SOURCE_PREFIX):
        kind = _SKIP
    else:
        layer, _, rule = source.rpartition(":")
        if not layer:
            kind = _SKIP
        elif rule in const.MATCH_WITHIN_RULES:
            kind = WITHIN
        else:
            kind = (Relation.OFFSHORE if rule == const.OFFSHORE else Relation.NEAR, rule)
    if source is not None:
        _KINDS[source] = kind
    return kind


def _distance(place, rule, lat, lon):
    box = place.bbox
    if place.point is not None and not (rule == const.NEAREST and box is not None):
        return round(_km(lat, lon, place.point.lat, place.point.lon), 3)
    if box is None:
        return None
    km = _box_km(box, lat, lon)
    return round(km, 3) if km > 0 else None


def _box_km(box, lat, lon):
    """km from a point to the nearest point of a box (0 inside it)."""
    near_lat = min(max(lat, box.south), box.north)
    if box.crosses_antimeridian:
        inside_lon = lon >= box.west or lon <= box.east
    else:
        inside_lon = box.west <= lon <= box.east
    if inside_lon:
        return _km(lat, lon, near_lat, lon)
    return min(_km(lat, lon, near_lat, edge) for edge in (box.west, box.east))


def _km(lat1, lon1, lat2, lon2):
    """Great-circle km (haversine) on plain floats: placewise.geo.haversine without numpy's
    per-call overhead, for a handful of scalars per Result."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * MEAN_RADIUS_KM * math.asin(math.sqrt(min(max(a, 0.0), 1.0)))
