"""What a card shows: a title and (field, value, source) rows for a Result or an Entity, as plain
text that the text card (text.py) and the notebook table (html.py) lay out."""

from placewise.constants import display as const
from placewise.geo.distances import haversine


def card_rows(obj):
    """((title, aside), [(field, value, source or None)]) for a Result or an Entity: the title is the
    label or name, the aside its coordinates or context ("" when none); empty fields have no row."""
    from ..places import Entity

    return entity_rows(obj) if isinstance(obj, Entity) else result_rows(obj)


def result_rows(r):
    title = (r.label, f"({coords(r.lat, r.lon)})")
    out = []
    for field in const.RESULT_FIELDS:
        value = _RESULT_VALUES.get(field, _name)(getattr(r, field))
        if value:
            out.append((field, value, r.sources.get(field)))
    return title, out


def entity_rows(e):
    place = e.place
    where = ", ".join(x for x in (e.city, e.region, e.country) if x)
    title = (place.name, f"({where})" if where else "")
    kind = place.kind.value.replace("_", " ") + (f", tier {place.tier}" if place.tier else "")
    extent = f"{bbox_size(e.bbox)} box"
    if e.radius_km > 0:
        extent += f"{const.SEPARATOR}radius {km(e.radius_km)}"
    codes = {k: v for k, v in place.codes.items() if k not in const.ENTITY_HIDDEN_CODES}
    alternates = ""
    if e.alternates:
        ids = [p.id for p in e.alternates[: const.ALTERNATES_SHOWN]]
        more = [const.ELLIPSIS] if len(e.alternates) > const.ALTERNATES_SHOWN else []
        alternates = f"{len(e.alternates)}: " + ", ".join(ids + more)
    values = {
        "kind": (kind, None),
        "point": (coords(e.point.lat, e.point.lon), None),
        "extent": (extent, None),
        "id": (place.id, place.source),
        "score": (f"{e.score:.3f}" if e.score is not None else "", None),
        "codes": (", ".join(f"{k} {v}" for k, v in codes.items()), None),
        "aliases": (", ".join(place.aliases[: const.ALIASES_SHOWN]), None),
        "alternates": (alternates, None),
    }
    return title, [(f, *values[f]) for f in const.ENTITY_FIELDS if values[f][0]]


# -- values ---------------------------------------------------------------------------------------


def coords(lat, lon):
    return f"{lat:.{const.DECIMALS}f}, {lon:.{const.DECIMALS}f}"


def km(value):
    """ "9.0 km", "18 km": one decimal below 10 km, as the labels write it."""
    return f"{value:.0f} km" if value >= 10 else f"{value:.1f} km"


def bbox_size(box):
    """ "13.0 × 13.3 km": east-west across the middle latitude by north-south."""
    mid = (box.south + box.north) / 2
    span = box.east - box.west + (360.0 if box.crosses_antimeridian else 0.0)
    wide = 2 * float(haversine(mid, 0.0, mid, span / 2))  # halves: the short way round is the box's
    tall = float(haversine(box.south, 0.0, box.north, 0.0))
    return f"{_size(wide)} × {_size(tall)} km"


def nearby(n):
    """ "El Portal 18 km W", "on Lake Tahoe, shore 6.7 km E", "in the area of Gamma National Park"."""
    name = _name(n.place)
    relation = n.relation.value
    if relation in const.SHORE_RELATIONS and n.place.kind.value == "water":  # distance to the shore
        far = n.distance_km > const.HERE_KM
        return f"{relation} {name}" + (f", shore {_far(n)}" if far else "")
    if n.distance_km <= const.HERE_KM:
        return f"{relation} {name}" if relation in const.HERE_RELATIONS else f"{const.IN_AREA} {name}"
    return f"{name} {_far(n)}"


def _far(n):
    return " ".join(x for x in (km(n.distance_km), n.compass) if x)


def _size(value):
    return f"{value:.1f}" if value < 100 else f"{value:.0f}"


def _name(place):
    if place is None:
        return ""
    if isinstance(place, str):
        return place
    return place.name


def _coded(place, key):
    if place is None:
        return ""
    code = place.codes.get(key)
    return f"{place.name} ({code})" if code else place.name


def _places(places):
    return const.SEPARATOR.join(p.name for p in places)


def _near(near):
    return const.SEPARATOR.join(nearby(n) for n in near[: const.NEAR_SHOWN])


def _airport(n):
    return nearby(n).replace(n.place.name, _coded(n.place, "iata"), 1) if n is not None else ""


def _relative(rel):
    if rel is None:
        return ""
    return f"inside {rel.name}" if rel.inside else f"{km(rel.distance_km)} {rel.compass} of {rel.name}"


def _disputed(d):
    if d is None:
        return ""
    parts = [f"{d.name}: claimed by {', '.join(d.claimants)}"]
    if d.administered_by:
        parts.append(f"administered by {d.administered_by}")
    parts.append(f"{d.applied_view} view" + (" (locked)" if d.locked else ""))
    return "; ".join(parts)


_RESULT_VALUES = {
    "country": lambda p: _coded(p, "iso2"),
    "admin1": lambda p: _coded(p, "iso"),
    "regions": _places,
    "within": _places,
    "water": lambda n: nearby(n) if n is not None else "",
    "airport": _airport,
    "near": _near,
    "relative": _relative,
    "disputed": _disputed,
}
