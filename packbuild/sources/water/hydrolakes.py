"""HydroLAKES v1.0 (Messager et al. 2016, CC BY 4.0): lake and reservoir outlines, worldwide.

The polygons come as one 820 MB zip, ordered by `Hylak_id`, which runs from the largest lake to
the smallest: the lakes of at least `min_area_km2` are the file's first records (16,689 of
1,427,688 at 10 km²). `fetch_largest` reads the archive's directory, its .dbf (52 MB compressed)
and .shx, finds where the last kept record ends, and inflates the .shp member only that far
(packbuild.sources.water.ranged_zip), so the download is a fraction of the archive.

Names are sparse (1,837 of the 16,689 lakes of 10 km² or more) and bare ("Ontario", "Tahoe"):
`english_name` adds the generic ("Lake Ontario"); packbuild.sources.water.names joins better ones
from Natural Earth and Wikidata. HydroLAKES' `Country` is the country of the lake's outflow, so
Lake Ontario is "United States of America": it is never used (the country comes from the world
pack's polygons, with the worldview applied).
"""

import datetime as dt
import hashlib
import json
import logging
from pathlib import Path

from placewise.constants import water as const

from ...layer import LayerData
from . import shapes
from . import shp as _shp
from .ranged_zip import LocalZip, RangeIgnoredError, RemoteZip, download, open_range, open_whole

log = logging.getLogger(__name__)

SOURCE = "hydrolakes"
STEM = "HydroLAKES_polys_v10"
FOLDER = f"{STEM}_shp"
_RESERVOIR = 2  # Lake_type: 1 lake, 2 reservoir, 3 lake regulated by a dam


def fetch_largest(url, cache_dir, min_area_km2, refresh=False, opener=open_range, whole=open_whole):
    """(shp, dbf, count): a .shp holding the first `count` records, those of at least
    min_area_km2, and the archive's full .dbf; cached in <cache_dir>/HydroLAKES_polys_v10_shp/,
    each prefix with a .json sidecar (url, records, bytes, sha256, retrieval date). Read by range
    requests; a server ignoring them gets the whole archive downloaded there instead (`whole`),
    which is deleted as soon as the members are out."""
    folder = Path(cache_dir) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return _fetch(RemoteZip(url, opener=opener), url, folder, min_area_km2, refresh)
    except RangeIgnoredError as e:
        log.warning("%s; downloading the whole archive (about 820 MB), deleted once read", e)
        archive = download(url, folder / f"{FOLDER}.zip", whole)
        try:
            return _fetch(LocalZip(archive), url, folder, min_area_km2, refresh)
        finally:
            archive.unlink(missing_ok=True)


def _fetch(source, url, folder, min_area_km2, refresh):
    whole = {}
    for ext in (".dbf", ".shx", ".prj"):
        path = folder / f"{STEM}{ext}"
        if refresh or not path.exists():
            source.extract(f"{FOLDER}/{STEM}{ext}", path)
        whole[ext] = path
    areas = _shp.numbers(_shp.read_dbf(whole[".dbf"], fields=("Lake_area",))["Lake_area"])
    kept = (areas >= min_area_km2).nonzero()[0]
    count = int(kept[-1]) + 1 if len(kept) else 0
    if count == 0:
        raise ValueError(f"no HydroLAKES lake of {min_area_km2} km² or more")
    shp = folder / f"{STEM}.first{count}.shp"
    sidecar = shp.with_name(shp.name + ".json")
    if refresh or not (shp.exists() and sidecar.exists()):
        stop = int(_shp.record_ends(whole[".shx"])[count - 1])
        source.extract(f"{FOLDER}/{STEM}.shp", shp, limit=stop)
        meta = {
            "url": url,
            "member": f"{FOLDER}/{STEM}.shp",
            "records": count,
            "min_area_km2": min_area_km2,
            "bytes": stop,
            "sha256": hashlib.sha256(shp.read_bytes()).hexdigest(),
            "retrieved": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        }
        sidecar.write_text(json.dumps(meta, indent=2) + "\n")
    return shp, whole[".dbf"], count


def lakes(shp, dbf, count, tolerance_m):
    """The first `count` lakes as a lakes-layer LayerData (unnamed ones have name "")."""
    columns = _shp.read_dbf(dbf, limit=count, fields=("Hylak_id", "Lake_name", "Lake_type", "Lake_area"))
    ids, names, types, areas, features = [], [], [], [], []
    for parts, hylak, name, kind, area in zip(
        _shp.read_shapes(shp, limit=count), columns["Hylak_id"], columns["Lake_name"],
        _shp.numbers(columns["Lake_type"]), _shp.numbers(columns["Lake_area"]), strict=False,
    ):  # fmt: skip
        if parts is None:
            continue
        fid = f"hydrolakes:{hylak}"
        kind = const.RESERVOIR if kind == _RESERVOIR else const.LAKE
        ids.append(fid)
        names.append(english_name(name, kind))
        types.append(kind)
        areas.append(float(area))
        features.append(shapes.polygon_feature(parts, tolerance_m, fid))
    n = len(ids)
    columns = {
        "id": ids, "name": names, "type": types, "wikidata": [""] * n, "aliases": [""] * n,
        "source": [SOURCE] * n, "area_km2": areas,
    }  # fmt: skip
    types_ = {k: "str" for k in columns} | {"area_km2": "f8"}
    return LayerData(const.LAKES, "polygon", columns, (SOURCE,), features=features, types=types_)


def english_name(name, kind):
    """HydroLAKES' bare names with their generic: "Ontario" -> "Lake Ontario", a reservoir's
    "Kariba" -> "Kariba Reservoir"; names that already say what they are stay."""
    name = const.NAME_FIXES.get(name, name)
    if not name or set(name.split()) & set(const.WATER_WORDS):
        return name
    return f"{name} Reservoir" if kind == const.RESERVOIR else f"Lake {name}"
