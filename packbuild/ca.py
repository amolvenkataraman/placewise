"""The Canada pack: provinces, census divisions, census subdivisions (municipalities), CMAs/CAs and
forward sortation areas from Statistics Canada's 2021 Census, with 2021 populations.

    uv run python -m packbuild.ca --version 2026.11
    uv run python -m packbuild.ca --version 2026.11 --via service   # StatCan's map service instead

Downloads land once in .cache/packbuild/ (gitignored); the pack is written to --out.
"""

import argparse
import datetime as dt
import logging
import urllib.error
import urllib.parse
from pathlib import Path

from . import arcgis
from .fetch import DEFAULT_CACHE, fetch, unzip
from .layer import write_pack
from .sources import statcan, url

log = logging.getLogger(__name__)

VIAS = ("files", "service")
# layer name -> (source id, registry download name, loader)
LAYERS = {
    "provinces": (statcan.BOUNDARIES, "provinces", statcan.provinces),
    "cd": (statcan.BOUNDARIES, "cd", statcan.census_divisions),
    "csd": (statcan.BOUNDARIES, "csd", statcan.census_subdivisions),
    "cma": (statcan.BOUNDARIES, "cma", statcan.metro_areas),
    "fsa": (statcan.FSA, "fsa", statcan.forward_sortation_areas),
}
POPULATION_TABLES = ("csd", "cma", "fsa")


def build_layers(cache_dir, refresh=False, via="files", tolerance_m=statcan.DEFAULT_TOLERANCE_M):
    """The five Canada layers, fetching (or reusing) the source files in `cache_dir`. via="files"
    reads the zipped shapefiles; via="service" the same boundaries from StatCan's map service."""
    if via not in VIAS:
        raise ValueError(f"via must be one of {', '.join(VIAS)}, not {via!r}")

    def get(u):
        try:
            return fetch(u, cache_dir, refresh=refresh)
        except urllib.error.HTTPError as e:
            if e.code == 403 and via == "files":
                raise RuntimeError(
                    f"{u}: HTTP 403. www12.statcan.gc.ca answers scripted downloads with a browser "
                    "check; build with --via service (via='service') to read the same boundary files "
                    "from Statistics Canada's map service"
                ) from e
            raise

    def boundaries(source_id, name):
        zip_url = url(source_id, name)
        stem = Path(urllib.parse.urlparse(zip_url).path).stem  # e.g. lcsd000b21a_e
        if via == "service":
            return arcgis.fetch_layer(url(source_id, "service"), service_layer_name(stem), cache_dir, refresh)
        folder = unzip(get(zip_url))
        found = sorted(folder.rglob(f"{stem}.shp")) or sorted(folder.rglob("*.shp"))
        if len(found) != 1:
            raise ValueError(f"{folder}: expected one shapefile, found {[p.name for p in found]}")
        return found[0]

    tables = []
    for name in POPULATION_TABLES:
        archive = get(url(statcan.POPULATION, name))
        table = archive.stem.split("-")[0]  # 98100002-eng.zip holds 98100002.csv
        tables.append(unzip(archive) / f"{table}.csv")
    population = statcan.read_population(*tables)
    return [
        loader(boundaries(source_id, name), population, tolerance_m)
        for source_id, name, loader in LAYERS.values()
    ]


def service_layer_name(file_stem):
    """The map-service layer of a boundary file: the 11th character of StatCan's 13-character
    file names is the format, "a" for Shapefile and "s" for services (92-160-G, file naming)."""
    if len(file_stem) != 13:
        raise ValueError(f"{file_stem!r} is not a 13-character StatCan file name")
    return f"{file_stem[:10]}s{file_stem[11:]}"


def build_ca(
    cache_dir, out_dir, version, refresh=False, via="files", tolerance_m=statcan.DEFAULT_TOLERANCE_M
):
    """Fetch the sources, build the layers and write `<out_dir>/can-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh, via=via, tolerance_m=tolerance_m)
    for layer in layers:
        vertices = sum(len(r) for f in layer.features for o in f.outlines for r in o.rings)
        log.info("%s: %d features, %d vertices", layer.name, len(layer.columns["id"]), vertices)
    return write_pack(Path(out_dir), "can", version, layers)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.ca", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    parser.add_argument(
        "--via", choices=VIAS, default="files", help="boundary zips, or StatCan's map service"
    )
    parser.add_argument(
        "--tolerance-m",
        type=float,
        default=statcan.DEFAULT_TOLERANCE_M,
        help="simplification, metres (0: none)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_ca(args.cache_dir, args.out, args.version, args.refresh, args.via, args.tolerance_m)
    print(path)


if __name__ == "__main__":
    main()
