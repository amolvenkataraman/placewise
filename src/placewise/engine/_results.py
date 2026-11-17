"""Results from the vectorised answer: Places from the caches, sources, labels.

The label is "<name>, <admin1>, <country>", consecutive repeats dropped ("New York, United States"),
where <name> is the locality (label.style "locality", the default) or the city (style "city"),
each falling back to the other; label.template formats any field instead. Far offshore, the label
names a reference place: "Offshore, 15 km S of Toronto".
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.model import Nearby, PlaceKind, Relation, Result

from . import _nearby as nearby

NAMED = ("sublocality", "locality", "city", "borough", "admin2", "postal")


def build(geo, lat, lon, a, named, order, locked):
    """One Result per point. `named` holds the naming rules' object arrays (placewise.engine.naming):
    Places per field, `regions` tuples and `sources` dicts, None where they don't apply."""
    layers, admin = geo.layers, geo.admin
    n = len(lat)
    minus = np.full(n, -1, dtype=np.int64)
    city = a.get("city", minus)
    airport = a.get("airport", minus)
    cities_layer, airports_layer = layers.layer(const.CITIES), layers.layer(const.AIRPORTS)
    # every bearing and compass word at once; then plain lists, which index faster than arrays
    air_deg, air_word = nearby.bearings(airports_layer, lat, lon, airport)
    water_deg, water_word = nearby.water_bearings(a, lat, lon)
    far_city = np.where(a["cidx"] < 0, city, -1)
    back_word = nearby.bearings(cities_layer, lat, lon, far_city, reverse=True)[1]
    near_rows = nearby.near_rows(
        cities_layer, a, lat, lon, city, geo.settings.near.max_near, geo._near_km(PlaceKind.LOCALITY)
    )

    cidx, view, aidx, foreign = (a[k].tolist() for k in ("cidx", "view", "aidx", "foreign"))
    cmode, amode = a["cmode"].tolist(), a["amode"].tolist()
    city, far_city = city.tolist(), far_city.tolist()
    city_km = a.get("city_km", np.full(n, np.inf)).tolist()
    tz_row = a.get("tz", minus).tolist()
    airport, airport_km = airport.tolist(), a.get("airport_km", np.full(n, np.inf)).tolist()
    air_deg, air_word = air_deg.tolist(), air_word.tolist()
    water, water_km = a["water"].tolist(), a["water_km"].tolist()
    water_deg, water_word, back_word = water_deg.tolist(), water_word.tolist(), back_word.tolist()
    lats, lons = lat.tolist(), lon.tolist()
    tz_col = geo.cities.table["tz"] if layers.has(const.CITIES) else None
    applied = a.get("applied")
    view_rows = admin.worldviews.resolve(order)[0].tolist() if admin.worldviews is not None else None
    rules = (const.POLYGON, const.OFFSHORE, const.NEAREST, const.SCORE)
    src = {(role, rule): layers.source(role, rule) for role in _ROLES if layers.has(role) for rule in rules}
    place = layers.place
    # the place caches, read directly in the loop below (place() fills them on a miss)
    country_places, admin1_places, city_places = (layers.cache(r) for r in _ROLES[:3])
    named_lists = {k: v.tolist() for k, v in named.items()}
    empty = [None] * n
    sub_l, loc_l, city_l, bor_l, adm2_l, post_l = (named_lists.get(k, empty) for k in NAMED)
    regions_l, sources_l = named_lists.get("regions", empty), named_lists.get("sources", empty)
    results = []
    for i in range(n):
        ci, vi, ai = cidx[i], view[i], aidx[i]
        sources = {}
        country = admin1 = city_place = tz = air = water_near = disputed = None
        if vi >= 0:
            country = country_places.get(vi) or place(const.COUNTRIES, vi)
            sources["country"] = src[const.COUNTRIES, cmode[i]]
        if ai >= 0:
            admin1 = admin1_places.get(ai) or place(const.ADMIN1, ai)
            sources["admin1"] = src[const.ADMIN1, amode[i]]
        locality = None
        if ci >= 0:
            disputed = admin.disputed(ci, ai, foreign[i], applied, locked)
            if city[i] >= 0:
                city_place = locality = city_places.get(city[i]) or place(const.CITIES, city[i])
                sources["city"] = sources["locality"] = src[const.CITIES, const.SCORE]
            t = tz_row[i]
            if t >= 0 and tz_col[t]:
                tz = tz_col[t]
                sources["tz"] = src[const.CITIES, const.NEAREST]
        elif water[i] >= 0:
            w = view_rows[water[i]]
            water_near = Nearby(
                place(const.COUNTRIES, w if w >= 0 else water[i]), Relation.OFFSHORE,
                water_km[i], water_deg[i], water_word[i],
            )  # fmt: skip
            sources["water"] = src[const.COUNTRIES, const.NEAREST]
        if sources_l[i] is not None:  # the naming rules' fields replace the provisional ones
            city_place, locality = city_l[i], loc_l[i]
            for field in ("city", "locality"):
                sources.pop(field, None)
            sources.update(sources_l[i])
        if airport[i] >= 0:
            km = airport_km[i]
            rel = Relation.AT if km <= const.AIRPORT_AT_KM else Relation.NEAR
            air = Nearby(place(const.AIRPORTS, airport[i]), rel, km, air_deg[i], air_word[i])
            sources["airport"] = src[const.AIRPORTS, const.NEAREST]
        near = tuple(
            Nearby(place(const.CITIES, row), Relation.NEAR, km, deg, word)
            for row, km, deg, word in near_rows[i]
        )
        if sources_l[i] is not None:  # a census city's GeoNames twin isn't "near" it
            skip = {p.name for p in (city_place, locality) if p is not None}
            near = tuple(x for x in near if x.place.name not in skip)
        if near:
            sources["near"] = src[const.CITIES, const.NEAREST]
        fields = {
            "country": country, "admin1": admin1, "admin2": adm2_l[i], "city": city_place,
            "locality": locality, "sublocality": sub_l[i], "borough": bor_l[i], "postal": post_l[i],
            "regions": regions_l[i] or (), "airport": air, "water": water_near,
        }  # fmt: skip
        if ci >= 0:
            label = compose(geo.settings.label, fields)
        elif far_city[i] >= 0:
            ref = place(const.CITIES, far_city[i]).name
            label = f"{const.OFFSHORE_LABEL}, {nearby.km_text(city_km[i])} {back_word[i]} of {ref}"
        elif water_near is not None:
            word = nearby.opposite(water_near.compass)
            km = nearby.km_text(water_near.distance_km)
            label = f"{const.OFFSHORE_LABEL}, {km} {word} of {water_near.place.name}"
        else:
            label = const.OFFSHORE_LABEL
        results.append(
            Result(
                lat=lats[i], lon=lons[i], label=label, tz=tz, near=near, disputed=disputed, sources=sources,
                data_version=geo.data_version, **fields,
            )
        )  # fmt: skip
    return results


_ROLES = (const.COUNTRIES, const.ADMIN1, const.CITIES, const.AIRPORTS)


def compose(label_settings, fields):
    """The label from a Result's fields (a dict of them, or the Result itself)."""
    get = fields.get if isinstance(fields, dict) else lambda k: getattr(fields, k)
    city, locality = get("city"), get("locality")
    first = (locality, city) if label_settings.style == "locality" else (city, locality)
    name = next((p for p in first if p is not None), None)
    template = label_settings.template
    if not template:
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
    names["airport"] = get("airport").place.name if get("airport") else ""
    names["water"] = get("water").place.name if get("water") else ""
    text = template.format_map(_Blank(names))
    parts = [p.strip() for p in text.split(",")]
    return ", ".join(p for p in parts if p)


class _Blank(dict):
    def __missing__(self, key):
        return ""
