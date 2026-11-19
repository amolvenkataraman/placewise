"""The world-water pack: seas and oceans, lakes and reservoirs, rivers (docs/water.md).

    uv run python -m packbuild.water --version 2026.11

| Layer | Source |
|---|---|
| marine | Natural Earth 1:10m marine polygons (public domain) |
| lakes | HydroLAKES v1.0 outlines (CC BY 4.0) named from Natural Earth and Wikidata (CC0), and |
|       | Natural Earth's other lakes |
| rivers | Natural Earth 1:10m river centerlines, as zero-area polygons |

`--no-hydrolakes` builds the lakes from Natural Earth alone (no 220 MB of HydroLAKES downloads).
Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE); the pack is
written to --out.
"""

import argparse
import datetime as dt
import logging
from pathlib import Path

from placewise.constants import water as const

from . import names as name_index
from .fetch import DEFAULT_CACHE, add_keep_downloads, delete_downloads, fetch, unzip
from .layer import write_pack
from .sources import url
from .sources.water import hydrolakes, names
from .sources.water import naturalearth as ne
from .sources.water.ranged_zip import open_range

log = logging.getLogger(__name__)

NE_LAKES = ("lakes", "lakes_north_america", "lakes_europe")
NE_RIVERS = ("rivers", "rivers_north_america", "rivers_europe")
WIKIDATA_QUERIES = ("water_lakes", "water_reservoirs")
SPARQL_TIMEOUT_S = 120  # the query service gives up after 60 s; the lakes query takes ~45 s


def build_layers(cache_dir, refresh=False, with_hydrolakes=True, min_lake_km2=const.MIN_LAKE_KM2,
                 tolerance_m=const.LAKE_TOLERANCE_M, opener=open_range):  # fmt: skip
    """The marine, lakes and rivers layers, fetching (or reusing) the sources in `cache_dir`."""
    cache_dir = Path(cache_dir)

    def shapefile(name):
        archive = fetch(url(ne.SOURCE, name), cache_dir, refresh=refresh)
        return unzip(archive) / f"{archive.stem}.shp"

    marine = ne.marine(shapefile("marine"))
    lakes = ne.lakes([shapefile(n) for n in NE_LAKES])
    rivers = ne.rivers([shapefile(n) for n in NE_RIVERS])
    if with_hydrolakes:
        shp, dbf, count = hydrolakes.fetch_largest(
            url(hydrolakes.SOURCE, "polygons"), cache_dir, min_lake_km2, refresh=refresh, opener=opener
        )
        outlines = hydrolakes.lakes(shp, dbf, count, tolerance_m)
        queries = [
            fetch(url(names.WIKIDATA, q), cache_dir / "wikidata-water" / q, refresh, timeout=SPARQL_TIMEOUT_S)
            for q in WIKIDATA_QUERIES
        ]
        log.info("hydrolakes: %d outlines of %s km² or more", count, min_lake_km2)
        lakes = names.join(outlines, lakes, names.wikidata_points(queries), cache_dir / "tmp")
    return [marine, lakes, rivers]


def build_water(cache_dir, out_dir, version, refresh=False, **options):
    """Fetch the sources, build the layers and write `<out_dir>/world-water-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh, **options)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    names = name_index.for_pack("world-water", layers)
    return write_pack(Path(out_dir), const.PACK, version, layers, names=names)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.water", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    parser.add_argument("--no-hydrolakes", action="store_true", help="lakes from Natural Earth only")
    parser.add_argument(
        "--min-lake-km2", type=float, default=const.MIN_LAKE_KM2, help="smallest HydroLAKES lake kept"
    )
    parser.add_argument(
        "--tolerance-m", type=float, default=const.LAKE_TOLERANCE_M, help="lake outline simplification"
    )
    add_keep_downloads(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_water(
        args.cache_dir, args.out, args.version, refresh=args.refresh, with_hydrolakes=not args.no_hydrolakes,
        min_lake_km2=args.min_lake_km2, tolerance_m=args.tolerance_m,
    )  # fmt: skip
    print(path)
    delete_downloads(args)  # the raw downloads, once the pack is written


if __name__ == "__main__":
    main()
