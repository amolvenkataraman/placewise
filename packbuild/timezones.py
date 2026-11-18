"""The packs' time zones: the curated zone tables (placewise-data datasets/timezones/*.json,
CC BY 4.0) checked and written as a `tz` column on the admin layers the packs already carry, plus a
small `timezones` layer of the few hand-drawn shapes.

    countries, admin1, shapes = world_tables(load("world"), countries, admin1)   # Natural Earth units
    counties, shapes = country_tables(load("usa"), states, [counties], parent, aiannh, ("uscensus",))

216 of the tz database's 247 countries have one zone, so most of the world is a country with its
zone; the rest follow admin lines, so the tables map admin units to zones (`world.json`: Natural
Earth admin-1; `usa.json`: Census counties; `can.json`: StatCan divisions and subdivisions), each
entry citing tzdb or the law it follows, plus a few hand-drawn `shapes` (boxes or a polygon) where no
unit fits (Eucla, the western Aleutians) and, in the US, Census AIANNH areas (the Navajo Nation).

The zone goes on the unit's own row (column TZ_FIELD, placewise.constants.lookup): the world's
countries and admin-1 units each carry their own entry ("" when they have none); a country pack's
finest units (counties, census subdivisions) carry their resolved zone (their own, else their
division's, else their state's or province's), so the engine reads the zone of the unit it has
already found, and no unit's outline is copied. Only the shapes are drawn, in the `timezones`
layer, which the engine tests first. A unit whose entry is null (tzdb records no zone there: Bir
Tawil, Antarctica away from its stations) has TZ_NONE, and the engine falls back to the
nearest-city rule there. A zone may be a list: the unit is split along a line the pack doesn't draw;
the column joins them with TZ_SEPARATOR, and the engine lets the nearest town inside the unit whose
zone is listed decide (placewise.engine._timezones).

The build fails, listing every problem, on a zone the tz database doesn't have
(`zoneinfo.available_timezones()`), a unit of the layer without an entry, an entry naming a unit the
layer doesn't have or one of another country, a split country whose admin-1 units aren't all listed,
a split zone a country pack's finer units would inherit, an unknown source, or a malformed shape:
fix the dataset, never the build.
"""

import dataclasses
import json
import zoneinfo
from functools import cache

from placewise.constants.lookup import TZ_FIELD, TZ_NONE, TZ_SEPARATOR
from placewise.model import Feature, Outline

from . import datasets
from .layer import LayerData

LAYER = "timezones"
CURATED_SOURCE = "placewise-timezones"  # the curated dataset itself (CC BY 4.0), in the registry
SHAPE_PREFIX = "tz:"
# a few small shapes scattered over the world: coarse grid cells keep their index a few KB (1-degree
# cells would cost 0.8 MB for 23 boxes), and each cell holds one or two shapes to test
SHAPES_CELL_DEG = 10.0
COLUMNS = ("id", "name", "zone", "zones", "basis", "unit", "within", "country")
_ENTRY_KEYS = {"zone", "admin1", "parts", "sources", "notes"}
_SHAPE_KEYS = {"id", "name", "zone", "within", "boxes", "polygon", "aiannh", "sources", "notes"}


@cache
def known_zones():
    return frozenset(zoneinfo.available_timezones())


def load(name, folder=None):
    """One table, datasets/timezones/<name>.json ("world", "usa", "can")."""
    path = (folder or datasets.path("timezones")) / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def aiannh_codes(doc):
    """{shape id: Census AIANNHCE} of the shapes a country table draws from Census AIANNH areas."""
    return {s["id"]: s["aiannh"] for s in doc.get("shapes", ()) if "aiannh" in s}


# --- checks --------------------------------------------------------------------------------------


def check_entries(doc):
    """Problems in a table on its own (zones, sources, keys, shapes), as strings; [] if none."""
    problems, sources = [], set(doc.get("sources", {}))
    units = doc.get("countries", doc.get("admin1", {}))
    for uid, entry in units.items():
        problems += _check_entry(uid, entry, sources)
    seen = set()
    for shape in doc.get("shapes", ()):
        sid = shape.get("id", "?")
        if not sid.startswith(SHAPE_PREFIX):
            problems.append(f"{sid}: shape ids start with {SHAPE_PREFIX!r}")
        if sid in seen:
            problems.append(f"{sid}: listed twice")
        seen.add(sid)
        if unknown := set(shape) - _SHAPE_KEYS:
            problems.append(f"{sid}: unknown keys {', '.join(sorted(unknown))}")
        problems += _check_zone(sid, shape.get("zone"), allow_list=False)
        problems += _check_sources(sid, shape.get("sources", ()), sources)
        problems += _check_geometry(sid, shape)
    return problems


def _check_entry(uid, entry, sources):
    if not isinstance(entry, dict):
        return _check_zone(uid, entry)
    problems = []
    if unknown := set(entry) - _ENTRY_KEYS:
        problems.append(f"{uid}: unknown keys {', '.join(sorted(unknown))}")
    if "zone" in entry:
        problems += _check_zone(uid, entry["zone"])
    for sub, zone in {**entry.get("admin1", {}), **entry.get("parts", {})}.items():
        problems += _check_zone(sub, zone)
    return problems + _check_sources(uid, entry.get("sources", ()), sources)


def _check_zone(where, zone, allow_list=True):
    if zone is None:
        return []
    if isinstance(zone, list) and allow_list:
        if not zone:
            return [f"{where}: an empty list of zones"]
        if len(set(zone)) != len(zone):
            return [f"{where}: a zone listed twice"]
        return [p for z in zone for p in _check_zone(where, z, allow_list=False)]
    if not isinstance(zone, str) or zone not in known_zones():
        return [f"{where}: unknown zone {zone!r} (not in the tz database)"]
    return []


def _check_sources(where, named, sources):
    return [f"{where}: unknown source {s!r}" for s in named if s not in sources]


def _check_geometry(sid, shape):
    kinds = [k for k in ("boxes", "polygon", "aiannh") if k in shape]
    if len(kinds) != 1:
        return [f"{sid}: needs boxes or a polygon (or, in a country table, an aiannh code), exactly one"]
    try:
        shape_feature(shape) if kinds[0] != "aiannh" else None
    except (TypeError, ValueError) as e:
        return [f"{sid}: {e}"]
    return []


def _fail(problems):
    if problems:
        raise ValueError("time-zone table problems (fix datasets/timezones):\n  " + "\n  ".join(problems))


# --- geometry ------------------------------------------------------------------------------------


def shape_feature(shape):
    """A shape's Feature: `boxes` [[south, west, north, east], ...] or a `polygon` of [lat, lon]."""
    if "polygon" in shape:
        ring = tuple((float(lat), float(lon)) for lat, lon in shape["polygon"])
        if len(ring) < 3 or not all(abs(lat) <= 90 and abs(lon) <= 180 for lat, lon in ring):
            raise ValueError("bad polygon: three or more [lat, lon] points needed")
        return Feature((Outline((ring,)),))
    outlines = []
    for b in shape["boxes"]:
        s, w, n, e = (float(v) for v in b)
        if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
            raise ValueError(f"bad box {b}: [south, west, north, east] with south < north, west < east")
        outlines.append(Outline((((s, w), (s, e), (n, e), (n, w)),)))
    if not outlines:
        raise ValueError("bad box list: empty")
    return Feature(tuple(outlines))


def _joined(zone):
    """A table's zone as the `tz` column holds it: TZ_NONE for null, the list joined by TZ_SEPARATOR."""
    if zone is None:
        return TZ_NONE
    return TZ_SEPARATOR.join(zone) if isinstance(zone, list) else zone


def _shape_row(shape, within, country):
    return {
        "id": shape["id"], "name": shape.get("name", shape["id"]), "zone": shape["zone"], "zones": "",
        "basis": "shape", "unit": "", "within": within, "country": country,
    }  # fmt: skip


def _shapes_layer(rows, features, sources):
    """The `timezones` layer: the hand-drawn shapes alone (None when there are none)."""
    if not rows:
        return None
    columns = {c: [r[c] for r in rows] for c in COLUMNS}
    return LayerData(
        LAYER,
        "polygon",
        columns,
        (CURATED_SOURCE, *dict.fromkeys(sources)),
        features=[Feature(f.outlines, {}, r["id"]) for r, f in zip(rows, features, strict=True)],
        types={c: "str" for c in COLUMNS},
        cell_deg=SHAPES_CELL_DEG,
    )


def _with_zones(layer, zones):
    """`layer` with the `tz` column (and the curated dataset among its sources)."""
    return dataclasses.replace(
        layer,
        columns={**layer.columns, TZ_FIELD: zones},
        types={**layer.types, TZ_FIELD: "str"},
        sources=tuple(dict.fromkeys((*layer.sources, CURATED_SOURCE))),
    )


def _units(layer):
    """{id: (row index, name)} of a built LayerData."""
    return {uid: (i, layer.columns["name"][i]) for i, uid in enumerate(layer.columns["id"])}


# --- the world pack -----------------------------------------------------------------------------


def world_tables(doc, countries, admin1, sources=("naturalearth",)):
    """(countries, admin1, shapes) from world.json and the built Natural Earth `countries` and
    `admin1` LayerData (whose `adm0_a3` column says which country an admin-1 unit belongs to): the
    two with a `tz` column (placewise.constants.lookup.TZ_FIELD: a country's zone, "" for one split
    by admin-1 units; an admin-1 unit's own zone, "" for one that takes its country's), and the
    `timezones` layer of the hand-drawn shapes alone. The engine finds a point's zone from the
    units the admin answer found, so no unit's outline is copied."""
    problems = check_entries(doc)
    table = doc.get("countries", {})
    c_units, a_units = _units(countries), _units(admin1)
    adm0_of_country = dict(zip(countries.columns["id"], countries.columns["adm0_a3"], strict=True))
    country_of_adm0 = {a: cid for cid, a in adm0_of_country.items()}
    owner = {
        aid: country_of_adm0.get(a)
        for aid, a in zip(admin1.columns["id"], admin1.columns["adm0_a3"], strict=True)
    }
    problems += [f"{cid}: no entry" for cid in c_units if cid not in table]
    problems += [f"{cid}: not a unit of the countries layer" for cid in table if cid not in c_units]
    country_zone, admin1_zone = [""] * len(c_units), [""] * len(a_units)
    for cid, (ci, _) in c_units.items():
        entry = table.get(cid)
        entry = entry if isinstance(entry, dict) else {"zone": entry}
        listed = entry.get("admin1", {})
        for aid in listed:
            if aid not in a_units or owner.get(aid) != cid:
                problems.append(f"{cid}: {aid} is not one of its admin1 units")
        if "zone" not in entry:
            mine = [aid for aid, c in owner.items() if c == cid]
            problems += [f"{cid}: no zone for {aid}" for aid in mine if aid not in listed]
        for aid, zone in listed.items():
            if aid in a_units:
                admin1_zone[a_units[aid][0]] = _joined(zone)
        if "zone" in entry:
            country_zone[ci] = _joined(entry["zone"])
    shape_rows = []
    for shape in doc.get("shapes", ()):
        within = shape.get("within", "")
        country = within if within in c_units else owner.get(within)
        if country is None:
            problems.append(
                f"{shape.get('id')}: within {within!r} is no unit of the countries or admin1 layer"
            )
            continue
        shape_rows.append(_shape_row(shape, within, country))
    _fail(problems)
    features = [shape_feature(s) for s in doc.get("shapes", ())]
    return (
        _with_zones(countries, country_zone),
        _with_zones(admin1, admin1_zone),
        _shapes_layer(shape_rows, features, sources),
    )


# --- country packs ------------------------------------------------------------------------------


def country_tables(doc, admin1, parts, parent, shapes, sources, container=lambda pid, row: None):
    """(finest, shapes) from a country table (usa.json, can.json): `admin1` the pack's states or
    provinces LayerData, `parts` its finer unit layers, coarse to fine (counties; census divisions
    then subdivisions), `parent(part id, part row)` the admin-1 id a part lies in, `container(part
    id, part row)` the id of the coarser part it lies in (a subdivision's division) or None,
    `shapes` {shape id: Feature} for the shapes drawn from the pack's sources (Census AIANNH
    areas). `finest` is the last of `parts` with a `tz` column: each unit's own zone, else that of
    the listed part it lies in, else its admin-1 unit's, as the first of the shapes, parts and
    admin-1 units containing a point decided when each was drawn; `shapes` is the `timezones`
    layer of the shapes alone (None when the table has none). A split zone (a list) is never
    inherited: its nearest-town rule searches the unit it was given to."""
    problems = check_entries(doc)
    table = doc.get("admin1", {})
    country = f"iso:{doc.get('country', '')}"
    a_units = _units(admin1)
    part_units = {}
    for layer in parts:
        for i, pid in enumerate(layer.columns["id"]):
            part_units[pid] = {c: values[i] for c, values in layer.columns.items()}
    problems += [f"{aid}: no entry" for aid in a_units if aid not in table]
    problems += [f"{aid}: not a unit of the {admin1.name} layer" for aid in table if aid not in a_units]
    others = sorted({aid[4:6] for aid in a_units if aid.startswith("iso:")} - {doc.get("country")})
    if others:
        problems.append(f"{country}: the {admin1.name} layer's admin1 units are of {', '.join(others)}")
    zone_of = {}  # unit id -> its table zone (parts and admin-1 units)
    for aid in a_units:
        entry = table.get(aid)
        entry = entry if isinstance(entry, dict) else {"zone": entry}
        if entry.get("zone") is None and aid in table:
            problems.append(f"{aid}: needs a zone (null is for world units only)")
            continue
        for pid, zone in entry.get("parts", {}).items():
            if pid not in part_units:
                problems.append(f"{aid}: {pid} is not a unit of the pack")
            elif (home := parent(pid, part_units[pid])) != aid:
                problems.append(f"{aid}: {pid} lies in {home}")
            elif zone is not None:
                zone_of[pid] = zone
        if aid in table:
            zone_of[aid] = entry["zone"]
    finest = parts[-1]
    zones = []
    for pid in finest.columns["id"]:
        row = part_units[pid]
        chain = [pid, container(pid, row), parent(pid, row)]
        unit = next((u for u in chain if u in zone_of), None)
        zone = zone_of.get(unit, "")
        if isinstance(zone, list) and unit != pid:
            problems.append(f"{unit}: a split zone (a list) would pass to {pid}; list the zones of its parts")
        zones.append(_joined(zone) if unit is not None else "")
    shape_rows, features = [], []
    for shape in doc.get("shapes", ()):
        feature = shapes.get(shape.get("id")) if "aiannh" in shape else None
        if "aiannh" in shape and feature is None:
            problems.append(f"{shape.get('id')}: no geometry for AIANNH area {shape['aiannh']}")
            continue
        if feature is None and not _check_geometry(shape.get("id"), shape):
            feature = shape_feature(shape)
        if feature is not None:
            shape_rows.append(_shape_row(shape, "", country))
            features.append(feature)
    _fail(problems)
    return _with_zones(finest, zones), _shapes_layer(shape_rows, features, sources)
