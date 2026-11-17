"""The world pack: countries and admin-1 polygons (Natural Earth), cities (GeoNames) and airports
(OurAirports).

    uv run python -m packbuild.world --version 2026.11

Downloads land once in .cache/packbuild/ (gitignored); the pack is written to --out.
"""

import argparse
import datetime as dt
import logging
from pathlib import Path

from .fetch import DEFAULT_CACHE, fetch, unzip
from .layer import write_pack
from .sources import geonames, naturalearth, ourairports, url

log = logging.getLogger(__name__)


def build_layers(cache_dir, refresh=False):
    """The four world layers, fetching (or reusing) the source files in `cache_dir`."""

    def get(url):
        return fetch(url, cache_dir, refresh=refresh)

    def shapefile(url):
        archive = get(url)
        return unzip(archive) / f"{archive.stem}.shp"

    countries = naturalearth.countries(shapefile(url("naturalearth", "countries")))
    admin1 = naturalearth.admin1(shapefile(url("naturalearth", "admin1")))
    cities_zip = get(url("geonames", "cities"))
    cities = geonames.cities(
        unzip(cities_zip) / f"{cities_zip.stem}.txt",
        get(url("geonames", "admin1_codes")),
        get(url("geonames", "country_info")),
    )
    airports = ourairports.airports(get(url("ourairports", "airports")))
    return [countries, admin1, cities, airports]


def build_world(cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the layers and write `<out_dir>/world-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), "world", version, layers)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.world", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_world(args.cache_dir, args.out, args.version, refresh=args.refresh)
    print(path)


if __name__ == "__main__":
    main()
