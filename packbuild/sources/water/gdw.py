"""Global Dam Watch v1.0 (Lehner et al. 2024, CC BY 4.0): reservoir outlines, worldwide, as the
world-water pack's `reservoirs` layer.

The archive (70 MB from figshare) holds 41,145 barriers and 35,295 reservoir polygons with
`RES_NAME`, `DAM_NAME`, `ALT_NAME`, `LAKE_CTRL` and `AREA_POLY` (km²); only the reservoir .shp and
.dbf are extracted. Kept: reservoirs of at least `min_area_km2` (the lakes' threshold) with a name,
built as reservoirs (`LAKE_CTRL` empty: a natural lake raised by a control dam, Lake Tahoe, stays a
lake), simplified like the lakes.

Names: the reservoir's own when it says it is water ("Lake Mead"); a bare one takes the dam's
when that does ("Nagarjuna" -> "Nagarjuna Sagar"), else "Reservoir" ("Hirakud Reservoir"); with no
reservoir name, the dam's without its "Dam" ("Tehri" -> "Tehri Reservoir", "El Vado Reservoir
Dam" -> "El Vado Reservoir"). packbuild.water drops the reservoirs a named lake already covers.
"""

import re
import zipfile
from pathlib import Path

from placewise.constants import water as const

from ...layer import LayerData
from . import shapes
from . import shp as _shp
from .naturalearth import _title

SOURCE = "gdw"
STEM = "GDW_reservoirs_v1_0"
_FIELDS = ("GDW_ID", "RES_NAME", "DAM_NAME", "ALT_NAME", "LAKE_CTRL", "AREA_POLY")
# a dam's name less the structure: "Big Meadows - Main Dam", "Eugene J. Burrell Lock and Dam"
_STRUCTURE = re.compile(
    r"(?:\s*-)?\s*\b(?:(?:main|lock\s+and|lock\s*&)\s+)?(?:dams?|barrage|dike|dyke|weir)$", re.IGNORECASE
)


def extract(archive, folder):
    """The reservoirs' .shp (and .dbf beside it) taken from the GDW archive into `folder`, once."""
    folder = Path(folder)
    shp = folder / f"{STEM}.shp"
    with zipfile.ZipFile(archive) as z:
        members = {Path(m).name: m for m in z.namelist()}
        for ext in (".shp", ".dbf"):
            target = folder / f"{STEM}{ext}"
            if not target.exists():
                folder.mkdir(parents=True, exist_ok=True)
                part = target.with_name(target.name + ".part")
                part.write_bytes(z.read(members[f"{STEM}{ext}"]))
                part.replace(target)
    return shp


def reservoirs(shp, min_area_km2, tolerance_m):
    """The `reservoirs` LayerData (the lakes layer's columns), smallest first."""
    shp = Path(shp)
    c = _shp.read_dbf(shp.with_suffix(".dbf"), fields=_FIELDS)
    area = _shp.numbers(c["AREA_POLY"])
    rows = []
    for i, parts in enumerate(_shp.read_shapes(shp)):
        if parts is None or not area[i] >= min_area_km2 or c["LAKE_CTRL"][i]:
            continue
        name = english_name(c["RES_NAME"][i], c["DAM_NAME"][i])
        if not name:
            continue
        fid = f"gdw:{c['GDW_ID'][i]}"
        alias = _title(c["ALT_NAME"][i])
        rows.append((float(area[i]), fid, name, alias if alias != name else "", parts))
    rows.sort(key=lambda r: r[0])
    n = len(rows)
    columns = {
        "id": [r[1] for r in rows], "name": [r[2] for r in rows], "type": [const.RESERVOIR] * n,
        "wikidata": [""] * n, "aliases": [r[3] for r in rows], "source": [SOURCE] * n,
        "area_km2": [r[0] for r in rows],
    }  # fmt: skip
    features = [shapes.polygon_feature(r[4], tolerance_m, r[1]) for r in rows]
    types = {k: "str" for k in columns} | {"area_km2": "f8"}
    return LayerData(const.RESERVOIRS, "polygon", columns, (SOURCE,), features=features, types=types)


def english_name(res_name, dam_name):
    """The display name from GDW's reservoir and dam names ("" when neither gives one)."""
    res = _title(const.NAME_FIXES.get(res_name, res_name))
    dam = const.NAME_FIXES.get(dam_name, dam_name)
    if dam == dam_name:  # a fixed name is final; others lose the structure's word
        dam = _STRUCTURE.sub("", _title(dam)).strip(" -")
    if res:
        if _says_water(res):
            return res
        return dam if dam.startswith(res) and _says_water(dam) else f"{res} Reservoir"
    if {w.lower() for w in dam.split()} & const.DAM_STRUCTURE_WORDS:
        return ""
    if not dam or _says_water(dam):
        return dam
    return f"{dam} Reservoir"


def _says_water(name):
    return bool(set(name.split()) & set(const.WATER_WORDS))
