"""The world-towns pack: town and city outlines world-wide, from the GHS-SMOD 2020 grid (JRC,
CC BY 4.0), named from the world pack's GeoNames places (packbuild.sources.ghsl.towns).

    uv run python -m packbuild.towns --version 2026.11   # out/world-towns-2026.11/

Optional, beside the world pack it is built from (`--world`, default the world pack of the same
version in --out): its countries cut the clusters, its cities name them, and the lookup turns an
outline back into that city. The US, Canada and India are left out; their packs name places.
"""

import argparse
import datetime as dt
import logging
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import towns as const
from placewise.packs import IdTemplate, open_pack

from .fetch import DEFAULT_CACHE, add_keep_downloads, delete_downloads, fetch
from .layer import LayerData, write_pack
from .sources import url
from .sources.ghsl.geotiff import GeoTiff
from .sources.ghsl.towns import CENTRE, NO_POPULATION, TOWN, outlines
from .sources.water.shp import numbers, read_dbf

log = logging.getLogger(__name__)

SOURCE = "ghsl"
ABOUT = {"kind": "towns", "covers": list(const.COVERS), "requires": [lookup_const.DEFAULT_PACK]}
# the ids outlines() makes (ghs:<country>:<GeoNames number>), rebuilt by readers from the columns
ID_TEMPLATE = IdTemplate("ghs:{country}:{geonames:tail}")
TOLERANCE_M = 400.0  # outline simplification; the cells are 1 km
CHUNK = 250_000  # cell centres given a country at once
_EXTRACTS = (("_UC_", CENTRE), ("_DUC_", TOWN))  # vector extracts in the zip: their populations


def country_codes(world):
    """country_of(lon, lat) over the world pack: the de facto country code of each point, with
    the lookups' 12 nmi offshore reach ("" where none)."""
    from placewise.engine._admin import Admin
    from placewise.engine._layers import Layers

    admin = Admin(Layers([world]))
    codes = np.array([*admin.worldviews.code, ""], dtype=object)

    def country_of(lon, lat):
        out = np.empty(len(lon), dtype=object)
        for s in range(0, len(lon), CHUNK):
            a = {}
            admin.answer(a, lat[s : s + CHUNK], lon[s : s + CHUNK], (lookup_const.DE_FACTO,))
            view = a["view"]
            out[s : s + CHUNK] = codes[np.where(view >= 0, view, len(codes) - 1)]
        return out

    return country_of


def world_cities(world):
    """The columns of the world pack's `cities` layer the naming reads."""
    layer = world[lookup_const.CITIES]
    columns = {f: layer.column(f).tolist() for f in ("id", "name", "country", "feature_code")}
    columns["population"] = np.asarray(layer.column("population"), dtype=np.float64)
    columns["lat"], columns["lon"] = np.asarray(layer.lat), np.asarray(layer.lon)
    return columns


def read_zip(archive):
    """(GeoTiff, centroids) from the GHS-SMOD zip: the grid and the vector extracts' populations."""
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        tif = GeoTiff(z.read(next(n for n in names if n.endswith(".tif"))))
        if "Mollweide" not in tif.crs_text:
            raise ValueError(f"{archive.name}: expected the World Mollweide grid, got {tif.crs_text[:80]!r}")
        parts = []
        with tempfile.TemporaryDirectory() as tmp:
            for tag, group in _EXTRACTS:
                member = next(n for n in names if tag in n and n.endswith(".dbf"))
                path = Path(tmp) / "extract.dbf"
                path.write_bytes(z.read(member))
                table = read_dbf(path, fields=("POP_2020", "PWCentr_X", "PWCentr_Y"))
                pop = numbers(table["POP_2020"])
                parts.append(
                    (np.full(len(pop), group), pop, numbers(table["PWCentr_X"]), numbers(table["PWCentr_Y"]))
                )
    centroids = tuple(np.concatenate([p[k] for p in parts]) for k in range(4))
    return tif, centroids


def build_layer(archive, world, tolerance=TOLERANCE_M):
    """The `towns` LayerData from the GHS-SMOD zip and the opened world pack."""
    tif, centroids = read_zip(archive)
    features, columns = outlines(
        tif, country_codes(world), world_cities(world), centroids=centroids, excluded=const.LEFT_OUT,
        tolerance=tolerance,
    )  # fmt: skip
    types = {
        "id": "str",
        "name": "str",
        "geonames": "str",
        "class": "str",
        "country": "str",
        "population": "i4",
    }
    columns["population"] = columns["population"].astype(np.int32)
    return LayerData(
        const.LAYER, "polygon", columns, (SOURCE, "geonames"), features=features, types=types,
        nulls={"population": NO_POPULATION}, id_template=ID_TEMPLATE,
    )  # fmt: skip


def build(cache_dir, out_dir, version, world_dir=None, refresh=False, tolerance=TOLERANCE_M):
    """Fetch GHS-SMOD, build the layer and write `<out_dir>/world-towns-<version>/`."""
    started = time.monotonic()
    world = open_pack(world_dir or Path(out_dir) / f"{lookup_const.DEFAULT_PACK}-{version}")
    archive = fetch(url(SOURCE, "smod"), Path(cache_dir) / "ghsl", refresh=refresh, timeout=120)
    layer = build_layer(archive, world, tolerance)
    log.info("towns: %d outlines in %.0f s", len(layer.columns["id"]), time.monotonic() - started)
    return write_pack(Path(out_dir), const.PACK, version, [layer], about=ABOUT)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.towns", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--world", type=Path, help="world pack directory (default: <out>/world-<version>)")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    parser.add_argument("--tolerance-m", type=float, default=TOLERANCE_M, help="outline simplification")
    add_keep_downloads(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(build(args.cache_dir, args.out, args.version, args.world, args.refresh, args.tolerance_m))
    delete_downloads(args)  # the raw downloads, once the pack is written


if __name__ == "__main__":
    main()
