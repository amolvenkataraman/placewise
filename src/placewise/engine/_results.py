"""Results from the vectorised answer: Places from the caches, sources, labels.

The label is "<name>, <admin1>, <country>", consecutive repeats dropped ("New York, United States"),
where <name> is the locality (label.style "locality", the default) or the city (style "city"),
each falling back to the other; in a national or state park (_within.label_park) it is "<name>,
<park>", or the park alone without one (label.parks, on by default); label.template formats any
field instead. Far offshore, the label names a reference place: "Offshore, 15 km S of Toronto".
On a sea or lake, the label names it ("Over Lake Ontario"; placewise.engine._water).
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.constants.worldviews import WORLDVIEW_RULE
from placewise.model import Nearby, PlaceKind, Relation, Result

from . import _nearby as nearby
from ._matches import matches
from ._notable import RADIUS
from ._within import label_park
from .naming.rules import same_name

NAMED = ("sublocality", "locality", "city", "borough", "admin2", "postal")


def build(geo, lat, lon, a, named, order, locked):
    """One Result per point. `named` holds the naming rules' object arrays (placewise.engine.naming):
    Places per field, `regions` tuples and `sources` dicts, None where they don't apply."""
    layers, admin = geo.layers, geo.admin
    n = len(lat)
    minus = np.full(n, -1, dtype=np.int64)
    land = a["cidx"] >= 0
    city = a.get("city", minus)
    airport = a.get("airport", minus)
    cities_layer, airports_layer = layers.layer(const.CITIES), layers.layer(const.AIRPORTS)
    # every bearing and compass word at once; then plain lists, which index faster than arrays
    air_deg, air_word = nearby.bearings(airports_layer, lat, lon, airport)
    water_deg, water_word = nearby.water_bearings(a, lat, lon)
    far_city = np.where(land, -1, city)
    back_word = nearby.bearings(cities_layer, lat, lon, far_city, reverse=True)[1]
    near_rows = nearby.near_rows(
        cities_layer, a, lat, lon, city, geo.settings.near.max_near, geo._near_km(PlaceKind.LOCALITY)
    )
    water_rows = geo.water.rows(a, lat, lon) if "wet_layer" in a else [None] * n
    # the Places of every point at once, each made once
    country_l = _places(layers, const.COUNTRIES, a["view"])
    admin1_l = _places(layers, const.ADMIN1, a["aidx"])
    city_l0 = _places(layers, const.CITIES, np.where(land, city, -1))
    tz_l = _tz(geo, a, land, minus)

    cidx = a["cidx"].tolist()
    cmode, amode = a["cmode"].tolist(), a["amode"].tolist()
    far_city = far_city.tolist()
    city_km = a.get("city_km", np.full(n, np.inf)).tolist()
    tz_zone, tz_source = (a[k].tolist() if k in a else [None] * n for k in ("tz_zone", "tz_source"))
    airport, airport_km = airport.tolist(), a.get("airport_km", np.full(n, np.inf)).tolist()
    air_deg, air_word = air_deg.tolist(), air_word.tolist()
    water, water_km = a["water"].tolist(), a["water_km"].tolist()
    water_deg, water_word, back_word = water_deg.tolist(), water_word.tolist(), back_word.tolist()
    lats, lons = lat.tolist(), lon.tolist()
    view_rows = admin.worldviews.resolve(order)[0].tolist() if admin.worldviews is not None else None
    rules = (const.POLYGON, const.OFFSHORE, const.NEAREST, const.SCORE, WORLDVIEW_RULE)
    src = {(role, rule): layers.source(role, rule) for role in _ROLES if layers.has(role) for rule in rules}
    src_country = {r: src[const.COUNTRIES, r] for r in rules if (const.COUNTRIES, r) in src}
    src_admin1 = {r: src[const.ADMIN1, r] for r in rules if (const.ADMIN1, r) in src}
    src_city, src_tz = src.get((const.CITIES, const.SCORE)), src.get((const.CITIES, const.NEAREST))
    place = layers.place
    named_lists = {k: v.tolist() for k, v in named.items()}
    empty = [None] * n
    sub_l, loc_l, city_l, bor_l, adm2_l, post_l = (named_lists.get(k, empty) for k in NAMED)
    regions_l, sources_l = named_lists.get("regions", empty), named_lists.get("sources", empty)
    parks = a.get("parks")  # (within, near, sources) per point (placewise.engine._within)
    notable = a.get("notable_places")  # (near, layer key) per point (placewise.engine._notable)
    label_settings, data_version = geo.settings.label, geo.data_version
    by_locality, template = label_settings.style == "locality", label_settings.template
    park_labels = label_settings.parks and not template
    # (id(name), id(admin1), id(country)) or (id(name), id(park)) -> label: Places outlive the loop
    labels = {}
    results = []
    for i in range(n):
        ci = cidx[i]
        sources = {}
        country, admin1 = country_l[i], admin1_l[i]
        tz = air = water_near = disputed = None
        if country is not None:
            sources["country"] = src_country[cmode[i]]
        if admin1 is not None:
            sources["admin1"] = src_admin1[amode[i]]
        city_place = locality = city_l0[i]
        if ci >= 0:
            disputed = admin.disputed(a, i, locked)
            if city_place is not None:
                sources["city"] = sources["locality"] = src_city
            if tz_zone[i] is not None:  # the timezones polygons (_timezones)
                tz = tz_zone[i]
                sources["tz"] = tz_source[i]
            elif tz_l[i]:
                tz = tz_l[i]
                sources["tz"] = src_tz
        elif water[i] >= 0:
            w = view_rows[water[i]]
            water_near = Nearby(
                place(const.COUNTRIES, w if w >= 0 else water[i]), Relation.OFFSHORE,
                water_km[i], water_deg[i], water_word[i],
            )  # fmt: skip
            sources["water"] = src[const.COUNTRIES, const.NEAREST]
        named_sources = sources_l[i]
        if named_sources is not None:  # the naming rules' fields replace the provisional ones
            city_place, locality = city_l[i], loc_l[i]
            sources.pop("city", None)
            sources.pop("locality", None)
            sources.update(named_sources)
        if airport[i] >= 0:
            km = airport_km[i]
            rel = Relation.AT if km <= const.AIRPORT_AT_KM else Relation.NEAR
            air = Nearby(place(const.AIRPORTS, airport[i]), rel, km, air_deg[i], air_word[i])
            sources["airport"] = src[const.AIRPORTS, const.NEAREST]
        near = ()
        if near_rows[i]:
            near = tuple(
                Nearby(place(const.CITIES, row), Relation.NEAR, km, deg, word)
                for row, km, deg, word in near_rows[i]
            )
            sources["near"] = src[const.CITIES, const.NEAREST]
        within = ()
        if parks is not None:
            within, park_near, park_sources = parks[i]
            near += park_near
            for field, rule in park_sources.items():
                sources.setdefault(field, rule)
        if notable is not None and notable[i][0]:
            near += _new_places(notable[i][0], within, near)
            sources.setdefault("near", layers.source(notable[i][1], RADIUS))
        fields = {
            "country": country, "admin1": admin1, "admin2": adm2_l[i], "city": city_place,
            "locality": locality, "sublocality": sub_l[i], "borough": bor_l[i], "postal": post_l[i],
            "regions": regions_l[i] or (), "within": within, "airport": air, "water": water_near,
        }  # fmt: skip
        if ci >= 0:
            if template:
                label = compose(label_settings, fields)
            else:
                first, second = (locality, city_place) if by_locality else (city_place, locality)
                park = label_park(within) if park_labels else None
                if park is None:
                    key = (id(first if first is not None else second), id(admin1), id(country))
                else:
                    key = (id(first), id(second), id(park))
                label = labels.get(key)
                if label is None:
                    label = labels[key] = compose(label_settings, fields)
        elif far_city[i] >= 0:
            ref = place(const.CITIES, far_city[i]).name
            label = f"{const.OFFSHORE_LABEL}, {nearby.km_text(city_km[i])} {back_word[i]} of {ref}"
        elif water_near is not None:
            word = nearby.opposite(water_near.compass)
            km = nearby.km_text(water_near.distance_km)
            label = f"{const.OFFSHORE_LABEL}, {km} {word} of {water_near.place.name}"
        else:
            label = const.OFFSHORE_LABEL
        if water_rows[i] is not None:  # on a sea or lake, or beside water (placewise.engine._water)
            label, near = water_rows[i].apply(fields, label, near, sources, ci >= 0)
        results.append(
            Result(
                lat=lats[i], lon=lons[i], label=label, tz=tz, near=near, disputed=disputed, sources=sources,
                matches=matches(fields, sources, lats[i], lons[i]), data_version=data_version, **fields,
            )
        )  # fmt: skip
    return results


_ROLES = (const.COUNTRIES, const.ADMIN1, const.CITIES, const.AIRPORTS)


def _new_places(found, within, near):
    """The notable Nearbys not already named (a park the point is in, a city or park near it)."""
    named = {p.name for p in within} | {n.place.name for n in near}
    return tuple(n for n in found if n.place.name not in named)


def _places(layers, key, rows):
    """The Place of each layer row as a list, None where the row is -1; each Place made once."""
    rows = np.asarray(rows)
    out = np.full(len(rows), None, dtype=object)
    have = np.flatnonzero(rows >= 0)
    if len(have):
        unique, inverse = np.unique(rows[have], return_inverse=True)
        made = np.empty(len(unique), dtype=object)
        made[:] = [layers.place(key, r) for r in unique.tolist()]
        out[have] = made[inverse.ravel()]
    return out.tolist()


def _tz(geo, a, land, minus):
    """Each land point's time zone name ("" or None where it has none)."""
    tz_row = a.get("tz", minus)
    if not geo.layers.has(const.CITIES) or geo.cities.table["tz"] is None:
        return [None] * len(land)
    names = geo.cities.table["tz"]
    ok = land & (tz_row >= 0)
    out = np.full(len(land), None, dtype=object)
    out[ok] = names[tz_row[ok]]
    return out.tolist()


def compose(label_settings, fields):
    """The label from a Result's fields (a dict of them, or the Result itself)."""
    get = fields.get if isinstance(fields, dict) else lambda k: getattr(fields, k)
    city, locality = get("city"), get("locality")
    first = (locality, city) if label_settings.style == "locality" else (city, locality)
    name = next((p for p in first if p is not None), None)
    template = label_settings.template
    if not template:
        park = label_park(get("within") or ()) if label_settings.parks else None
        if park is not None:  # "Yosemite Valley, Yosemite National Park"
            local = _park_local(first, park)
            if local is None or same_name(local.name, park.name):
                return park.name
            return f"{local.name}, {park.name}"
        parts = []
        for p in (name, get("admin1"), get("country")):
            if p is not None and p.name and (not parts or parts[-1] != p.name):
                parts.append(p.name)
        return ", ".join(parts)
    regions = get("regions")
    names = {
        k: (p.name if p is not None else "")
        for k in ("country", "admin1", "admin2", "city", "locality", "sublocality", "borough", "postal")
        for p in (get(k),)
    }
    names["locality"] = names["locality"] or names["city"]
    names["city"] = names["city"] or names["locality"]
    names["region"] = regions[0].name if regions else ""
    within = get("within")
    names["within"] = within[0].name if within else ""
    names["airport"] = get("airport").place.name if get("airport") else ""
    names["water"] = get("water").place.name if get("water") else ""
    text = template.format_map(_Blank(names))
    parts = [p.strip() for p in text.split(",")]
    return ", ".join(p for p in parts if p)


def _park_local(names, park):
    """The place a park label leads with: the style's own field (locality or city), else the other
    one when its point lies in the park's box (the GeoNames city "Yosemite Valley"; a town far
    outside the park would mislead); None: the park alone."""
    first, second = names
    if first is not None and first.name:
        return first
    inside = (
        second is not None and second.name and second.point is not None and park.bbox is not None
        and park.bbox.contains(second.point.lat, second.point.lon)
    )  # fmt: skip
    return second if inside else None


class _Blank(dict):
    def __missing__(self, key):
        return ""
