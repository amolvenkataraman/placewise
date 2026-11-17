"""Natural Earth 1:10m physical vectors (public domain): the world-water pack's `marine`, `lakes`
and `rivers` layers (packbuild.water).

- marine (`geography_marine_polys`): 306 polygons covering the oceans (sea, gulf, bay, strait ...,
  each ocean split in halves). English names: `name_en` (from Wikidata labels), except oceans and
  rivers keep `name` ("North Atlantic Ocean", not "Atlantic Ocean"), as do the few in
  constants.water.NE_KEEP_NAME. Records sharing an `ne_id` (the Great Barrier Reef) are one
  feature; unnamed polygons ("Internal Canada Waters") are left out.
- lakes (`lakes` + the `lakes_north_america` / `lakes_europe` supplements): `name` keeps the
  generic ("Lake Ontario", where `name_en` says "Ontario"); reservoirs named "<X> Dam" become "<X>"
  or "<X> Reservoir". Unnamed lakes are left out (nothing to say "On ..." with).
- rivers (`rivers_lake_centerlines` + supplements): river lines, the stretches of one river
  (same Wikidata id, else same name in one file) joined into one feature, as zero-area polygons
  (packbuild.sources.water.shapes). "Lake Centerline" stretches are left out: the lake answers.

Ids are "wikidata:Q..." when the Wikidata id is unique in the layer, else "ne:<ne_id>". Polygon
layers are sorted smallest first, so a bay inside a sea answers before the sea.
"""

from pathlib import Path

from placewise.constants import water as const
from placewise.model import Feature

from ...layer import LayerData
from . import shapes
from . import shp as _shp

SOURCE = "naturalearth-physical"


def marine(shp_path):
    groups = _by_ne_id(_rows(shp_path))
    names, types, wikidata, aliases, features, ne_ids = [], [], [], [], [], []
    for ne_id, members in groups.items():
        r = members[0][1]
        kind = r.get("featurecla", "").lower()
        native, english = _title(r["name"]), r.get("name_en", "")
        keep = not english or kind in const.NE_KEEP_NAME_TYPES or r.get("wikidataid") in const.NE_KEEP_NAME
        name = native if keep else english
        name = const.NAME_FIXES.get(name, name)
        alts = [a for a in (native, *_split(r.get("namealt"))) if a and a != name]
        names.append(name)
        types.append(kind)
        wikidata.append(r.get("wikidataid", ""))
        aliases.append("|".join(dict.fromkeys(alts)))
        ne_ids.append(ne_id)
        features.append(_polygons([parts for parts, _ in members], ne_id))
    return _polygon_layer(
        const.MARINE,
        ne_ids,
        {"name": names, "type": types, "wikidata": wikidata, "aliases": aliases},
        features,
    )


def lakes(shp_paths, tolerance_m=0.0):
    names, types, wikidata, aliases, features, ne_ids = [], [], [], [], [], []
    for path in shp_paths:
        for ne_id, members in _by_ne_id(_rows(path)).items():
            r = members[0][1]
            kind = const.RESERVOIR if r.get("featurecla", "").lower() == "reservoir" else const.LAKE
            name = english_lake_name(r["name"], kind)
            names.append(name)
            types.append(kind)
            wikidata.append(r.get("wikidataid", ""))
            aliases.append("|".join(a for a in _split(r.get("name_alt")) if a != name))
            ne_ids.append(ne_id)
            features.append(_polygons([parts for parts, _ in members], ne_id, tolerance_m))
    columns = {"name": names, "type": types, "wikidata": wikidata, "aliases": aliases,
               "source": ["naturalearth"] * len(names)}  # fmt: skip
    return _polygon_layer(const.LAKES, ne_ids, columns, features)


def rivers(shp_paths):
    groups, owner = {}, {}  # owner: ne_id -> group key, so a stretch in two files counts once
    for path in shp_paths:
        for parts, r in _rows(path):
            if parts is None or not r.get("name") or "centerline" in r.get("featurecla", "").lower():
                continue
            ne_id = _ne_id(r)
            key = r.get("wikidataid") or owner.get(ne_id) or (Path(path).stem, r["name"])
            if ne_id is not None and owner.setdefault(ne_id, key) != key:
                continue  # the same stretch again, in a supplement
            groups.setdefault(key, []).append((parts, r))
    ids, names, wikidata, ranks, types, features = [], [], [], [], [], []
    for members in groups.values():
        r = members[0][1]
        qid = r.get("wikidataid", "")
        ids.append(f"wikidata:{qid}" if qid else f"ne:{_ne_id(r)}")
        names.append(english_river_name(r["name"], r.get("name_en", ""), r.get("name_full", "")))
        wikidata.append(qid)
        rank = _shp.numbers([r.get("scalerank", "")])[0]
        ranks.append(int(rank) if rank == rank else -1)
        types.append("canal" if r.get("featurecla", "").lower() == "canal" else const.RIVER)
        features.append(shapes.line_feature([p for parts, _ in members for p in parts], ids[-1]))
    columns = {"id": ids, "name": names, "type": types, "wikidata": wikidata, "scalerank": ranks}
    types_ = {k: "str" for k in columns} | {"scalerank": "i2"}
    return LayerData(const.RIVERS, "polygon", columns, (SOURCE,), features=features, types=types_,
                     nulls={"scalerank": -1})  # fmt: skip


def english_lake_name(name, kind):
    """The display name of a lake or reservoir: fixed typos, title case for all-capitals, and a
    reservoir's "<X> Dam" as "<X>" (when X names water: "Nagarjuna Sagar") or "<X> Reservoir"."""
    name = const.NAME_FIXES.get(name, _title(name))
    if kind == const.RESERVOIR and name.endswith(" Dam"):
        base = name[: -len(" Dam")]
        return base if base.split()[-1] in const.WATER_WORDS else f"{base} Reservoir"
    return name


def english_river_name(name, name_en="", name_full=""):
    """`name_full` when given ("Illinois River"); a translated bare `name_en` gains " River"
    ("Da" / "Black" -> "Black River"); otherwise Natural Earth's English name ("Ganges")."""
    if name_full:
        return name_full
    if name_en and name_en != name and not set(name_en.split()) & set(const.RIVER_WORDS):
        return f"{name_en} River"
    return name_en or name


def _rows(shp_path):
    shp = Path(shp_path)
    columns = _shp.read_dbf(shp.with_suffix(".dbf"))
    records = [dict(zip(columns, values, strict=True)) for values in zip(*columns.values(), strict=True)]
    return list(zip(_shp.read_shapes(shp), records, strict=True))


def _by_ne_id(rows):
    """{ne_id: [(parts, record), ...]} for the named records; Natural Earth draws some features as
    several records with one ne_id (the Great Barrier Reef, multi-part lakes)."""
    groups = {}
    for parts, r in rows:
        if parts is not None and r.get("name"):
            groups.setdefault(_ne_id(r) or f"row{len(groups)}", []).append((parts, r))
    return groups


def _ne_id(record):
    """The record's ne_id as digits (some files write "1159107011.000000000"), or None."""
    number = _shp.numbers([record.get("ne_id", "")])[0]
    return str(int(number)) if number == number else None


def _polygons(record_parts, fid, tolerance_m=0.0):
    """One Feature from several records' rings (each record's rings grouped on their own)."""
    outlines = []
    for parts in record_parts:
        outlines.extend(shapes.polygon_feature(parts, tolerance_m, None).outlines)
    return Feature(tuple(outlines), {}, fid)


def _polygon_layer(name, ne_ids, columns, features):
    """Ids from the Wikidata column where unique, then every row sorted by area, smallest first."""
    counts = {}
    for q in columns["wikidata"]:
        counts[q] = counts.get(q, 0) + 1
    ids = [
        f"wikidata:{q}" if q and counts[q] == 1 else f"ne:{n}"
        for q, n in zip(columns["wikidata"], ne_ids, strict=True)
    ]
    areas = [shapes.area_km2(f) for f in features]
    order = sorted(range(len(ids)), key=lambda i: areas[i])
    out = {"id": [ids[i] for i in order]}
    out.update({k: [v[i] for i in order] for k, v in columns.items()})
    out["area_km2"] = [areas[i] for i in order]
    feats = [Feature(features[i].outlines, {}, ids[i]) for i in order]
    types = {k: "str" for k in out} | {"area_km2": "f8"}
    return LayerData(name, "polygon", out, (SOURCE,), features=feats, types=types)


_SMALL_WORDS = frozenset({"of", "the", "and", "de", "del", "du", "la"})


def _title(text):
    """ "INDIAN OCEAN" -> "Indian Ocean", "GULF OF ADEN" -> "Gulf of Aden"; mixed case is kept."""
    if not text.isupper():
        return text
    words = text.title().split(" ")
    return " ".join(w.lower() if i and w.lower() in _SMALL_WORDS else w for i, w in enumerate(words))


def _split(value):
    return [v.strip() for v in (value or "").split("|") if v.strip()]
