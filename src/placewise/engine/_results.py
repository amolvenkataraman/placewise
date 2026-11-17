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
    # the Places of every point at once, each made once
    country_l = _places(layers, const.COUNTRIES, a["view"])
    admin1_l = _places(layers, const.ADMIN1, a["aidx"])
    city_l0 = _places(layers, const.CITIES, np.where(land, city, -1))
    tz_l = _tz(geo, a, land, minus)
    # admin.disputed answers None unless the polygon is disputed or the admin1 is another country's
    wv = admin.worldviews
    maybe_disputed = (
        (land & (wv.disputed[np.maximum(a["cidx"], 0)] | (a["foreign"] >= 0))).tolist() if wv else [False] * n
    )

    cidx, aidx, foreign = (a[k].tolist() for k in ("cidx", "aidx", "foreign"))
    cmode, amode = a["cmode"].tolist(), a["amode"].tolist()
    far_city = far_city.tolist()
    city_km = a.get("city_km", np.full(n, np.inf)).tolist()
    airport, airport_km = airport.tolist(), a.get("airport_km", np.full(n, np.inf)).tolist()
    air_deg, air_word = air_deg.tolist(), air_word.tolist()
    water, water_km = a["water"].tolist(), a["water_km"].tolist()
    water_deg, water_word, back_word = water_deg.tolist(), water_word.tolist(), back_word.tolist()
    lats, lons = lat.tolist(), lon.tolist()
    applied = a.get("applied")
    view_rows = wv.resolve(order)[0].tolist() if wv is not None else None
    rules = (const.POLYGON, const.OFFSHORE, const.NEAREST, const.SCORE)
    src = {(role, rule): layers.source(role, rule) for role in _ROLES if layers.has(role) for rule in rules}
    src_country = {r: src[const.COUNTRIES, r] for r in rules if (const.COUNTRIES, r) in src}
    src_admin1 = {r: src[const.ADMIN1, r] for r in rules if (const.ADMIN1, r) in src}
    src_city, src_tz = src.get((const.CITIES, const.SCORE)), src.get((const.CITIES, const.NEAREST))
    place = layers.place
    named_lists = {k: v.tolist() for k, v in named.items()}
    empty = [None] * n
    sub_l, loc_l, city_l, bor_l, adm2_l, post_l = (named_lists.get(k, empty) for k in NAMED)
    regions_l, sources_l = named_lists.get("regions", empty), named_lists.get("sources", empty)
    label_settings, data_version = geo.settings.label, geo.data_version
    by_locality, template = label_settings.style == "locality", label_settings.template
    labels = {}  # (id(name), id(admin1), id(country)) -> label: the Places outlive the loop
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
            if maybe_disputed[i]:
                disputed = admin.disputed(ci, aidx[i], foreign[i], applied, locked)
            if city_place is not None:
                sources["city"] = sources["locality"] = src_city
            tz = tz_l[i]
            if tz:
                sources["tz"] = src_tz
            else:
                tz = None
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
        admin2, sublocality, borough, postal = adm2_l[i], sub_l[i], bor_l[i], post_l[i]
        regions = regions_l[i] or ()
        if ci >= 0:
            if template:
                label = compose(label_settings, {
                    "country": country, "admin1": admin1, "admin2": admin2, "city": city_place,
                    "locality": locality, "sublocality": sublocality, "borough": borough, "postal": postal,
                    "regions": regions, "airport": air, "water": water_near,
                })  # fmt: skip
            else:
                first, second = (locality, city_place) if by_locality else (city_place, locality)
                name = first if first is not None else second
                key = (id(name), id(admin1), id(country))
                label = labels.get(key)
                if label is None:
                    fields = {"city": city_place, "locality": locality, "admin1": admin1, "country": country}
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
        results.append(
            Result(
                lat=lats[i], lon=lons[i], label=label, country=country, admin1=admin1, admin2=admin2,
                city=city_place, locality=locality, sublocality=sublocality, borough=borough,
                postal=postal, tz=tz, regions=regions, near=near, airport=air, water=water_near,
                disputed=disputed, sources=sources, data_version=data_version,
            )
        )  # fmt: skip
    return results


_ROLES = (const.COUNTRIES, const.ADMIN1, const.CITIES, const.AIRPORTS)


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
