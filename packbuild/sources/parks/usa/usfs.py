"""USDA Forest Service administrative forest boundaries (public domain): national forests.

`S_USA.AdministrativeForest` (the EDW shapefile, NAD83 longitude/latitude, read as WGS84: 1-2 m
apart in the US). An administrative forest is the unit the Forest Service runs and people name
("Shasta-Trinity National Forest"), which can join several proclaimed forests. Ids are
`usfs:<FORESTORGCODE>` (dBASE: FORESTORGC); the file is at full resolution, so rings are
simplified (Douglas-Peucker in Web Mercator metres, `tolerance_m` on the ground at the forest's
latitude) before unprojecting.
"""

import math
import re

import numpy as np

from placewise.constants.parks import STATE
from placewise.geo import to_web_mercator
from placewise.io.shapefile import _encoding, _read_dbf, _read_shp, prj_datum

from ....fetch import fetch as fetch_file
from ....fetch import unzip
from ... import url
from .. import tiers
from .._common import ParkRow, WebMercator, feature_of

SOURCE = "usfs-forests"
DEFAULT_TOLERANCE_M = 10.0
_GRASSLAND = re.compile(r"\bgrasslands?\b", re.IGNORECASE)


def fetch(cache_dir, refresh=False):
    """The cached, unzipped shapefile's .shp path."""
    archive = fetch_file(url(SOURCE, "forests"), cache_dir, refresh=refresh)
    return unzip(archive) / f"{archive.stem}.shp"


def parks(shp_path, tolerance_m=DEFAULT_TOLERANCE_M):
    """ParkRows for the administrative forests (tier 2), simplified to `tolerance_m`."""
    shp = shp_path.with_suffix(".shp")
    prj = shp.with_suffix(".prj")
    if prj.exists() and prj_datum(prj.read_text(encoding="utf-8", errors="replace"), prj.name) != "nad83":
        raise ValueError(f"{prj.name}: expected NAD83 longitude/latitude")
    records = _read_dbf(shp.with_suffix(".dbf"), _encoding(shp.with_suffix(".cpg")))
    rows = []
    for rings, props in zip(_read_shp(shp), records, strict=True):
        name = " ".join(str(props.get("FORESTNAME") or "").split())
        code = str(props.get("FORESTORGC") or "").strip()
        if rings is None or not code or not tiers.usable_name(name):
            continue
        lat_mid = float(np.mean([r[:, 1].mean() for r in rings]))
        projected = [np.column_stack(to_web_mercator(r[:, 1], r[:, 0])) for r in rings]
        # Mercator stretches by 1 / cos(latitude): the same ground tolerance is more Mercator metres
        tolerance = tolerance_m / max(math.cos(math.radians(lat_mid)), 0.1)
        feature = feature_of(projected, WebMercator, f"usfs:{code}", tolerance)
        if feature is None:
            continue
        designation = "National Grassland" if _GRASSLAND.search(name) else "National Forest"
        short = tiers.short_name(name, designation + ("s" if name.endswith("s") else ""))
        rows.append(
            ParkRow(
                f"usfs:{code}", name, STATE, designation, feature, SOURCE, (short,) if short else (), code
            )
        )
    return rows
