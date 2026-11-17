"""The US pack: states, counties, places (incorporated places and CDPs), metro/micro areas (cbsa),
combined statistical areas (csa) and ZIP Code Tabulation Areas (zcta), all from the US Census
Bureau (public domain).

    uv run python -m packbuild.us --version 2026.11

Downloads land once in .cache/packbuild/ (gitignored); the pack is written to --out.
"""

import argparse
import datetime as dt
import logging
from pathlib import Path

from .fetch import DEFAULT_CACHE, fetch, unzip
from .layer import write_pack
from .sources import url, uscensus

log = logging.getLogger(__name__)

SHAPEFILES = ("state", "county", "place", "cbsa", "csa", "zcta")
DOWNLOADS = (*SHAPEFILES, "gazetteer_place", "gazetteer_zcta", "population", "delineation")


def build_layers(cache_dir, refresh=False):
    """The six US layers, fetching (or reusing) the source files in `cache_dir`."""

    def get(name):
        return fetch(url(uscensus.SOURCE, name), cache_dir, refresh=refresh)

    def shapefile(name):
        archive = get(name)
        return unzip(archive) / f"{archive.stem}.shp"

    def gazetteer(name):
        archive = get(name)
        return uscensus.read_gazetteer(unzip(archive) / f"{archive.stem}.txt")

    delineation = uscensus.read_delineation(get("delineation"))
    population_csv = get("population")
    log.info("population estimates: July %d", uscensus.population_year(population_csv))
    layers = [
        uscensus.states(shapefile("state")),
        uscensus.counties(shapefile("county"), delineation),
        uscensus.places(
            shapefile("place"), gazetteer("gazetteer_place"), uscensus.read_population(population_csv)
        ),
        uscensus.cbsa(shapefile("cbsa"), delineation),
        uscensus.csa(shapefile("csa"), delineation),
    ]
    # polygons: ZIP lookups are point-in-area questions, which internal points can't answer
    layers.append(uscensus.zcta(shapefile("zcta"), gazetteer("gazetteer_zcta")))
    return layers


def build_us(cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the layers and write `<out_dir>/us-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), "us", version, layers)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.us", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_us(args.cache_dir, args.out, args.version, refresh=args.refresh)
    print(path)


if __name__ == "__main__":
    main()
