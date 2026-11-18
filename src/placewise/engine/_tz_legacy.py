"""Time zones from packs built before the zones moved onto the admin layers (2026-11): their
`timezones` layer copies each unit's outline, rows in priority order (shapes, finer parts, admin-1
units, countries), with columns zone, zones, basis, unit, within, country. placewise.engine.
_timezones answers from them as it did then:

- the world pack's layer: through the admin answer (`world_units` maps every countries and admin1
  row to its feature);
- a country pack's layer (one country): the first feature containing the point (`country_layers`);
- a layer of several countries in a pack without the countries layer: the first feature of the
  point's country containing it (`first_of_country`).
"""

import numpy as np

from placewise.constants import lookup as const


def world_units(tz, key):
    """Timezones._world_units for the world pack's old `timezones` layer `key`."""
    admin, layers = tz.admin, tz.layers
    c_row = (
        {cid: i for i, cid in enumerate(admin.countries.column("id"))} if admin.countries is not None else {}
    )
    a_row = admin.admin1_row_of_id
    country = np.full(len(c_row), -1, dtype=np.int64)
    admin1 = np.full(len(a_row), -1, dtype=np.int64)
    shapes, split = [], np.zeros(len(c_row), dtype=bool)
    col = {f: layers.column(key, f) for f in ("basis", "unit", "within", "country", "zones")}
    for f, basis in enumerate(col["basis"]):
        ci = c_row.get(col["country"][f], -1)
        if basis == "country" and ci >= 0 and country[ci] < 0:
            country[ci] = f
        elif basis == "admin1" and col["unit"][f] in a_row:
            admin1[a_row[col["unit"][f]]] = f
        elif basis == "shape" and ci >= 0:
            shapes.append((f, ci, a_row.get(col["within"][f], -1)))
        if ci >= 0 and (basis != "country" or col["zones"][f]):
            split[ci] = True
    zone = layers.column(key, "zone")
    sole = np.array([zone[f] if f >= 0 and not split[i] else "" for i, f in enumerate(country)], dtype=object)
    return {"country": country, "admin1": admin1, "shapes": shapes, "sole": sole, "keys": (key, key, key)}


def country_layers(tz, a, lat, lon, todo):
    """Each one-country pack's old layer: the first feature containing the point, for the points in
    that country on ground whose data agrees."""
    iso2, agreed = tz.admin.iso2_of_view(a), tz.admin.undisputed(a)
    for key, country in tz.country_keys:
        pts = np.flatnonzero(todo & agreed & (iso2 == country.removeprefix("iso:")))
        if len(pts):
            feature = np.atleast_1d(tz.layers.layer(key).query(lat[pts], lon[pts]))
            tz._fill(a, key, pts, feature, const.POLYGON, lat, lon, todo)


def first_of_country(tz, key, a, pts, lat, lon):
    """Per point, the first feature of layer `key` that contains it and belongs to its country."""
    out = np.full(len(pts), -1, dtype=np.int64)
    if not len(pts) or tz.admin.countries is None:
        return out
    point, feature = tz.layers.layer(key).query_every(lat[pts], lon[pts])
    own_id = np.asarray(tz.admin.countries.column("id"), dtype=object)[a["cidx"][pts]]
    feature_country = np.asarray(tz.layers.column(key, "country"), dtype=object)
    keep = feature_country[feature] == own_id[point]
    point, feature = point[keep], feature[keep]
    first = np.flatnonzero(np.diff(point, prepend=-1))  # sorted by point, then feature
    out[point[first]] = feature[first]
    return out
