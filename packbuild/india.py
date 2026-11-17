"""The India pack: PIN code areas and post offices (Department of Posts, GODL-India), and the
curated regions (Delhi NCR ...) as unions of PIN code areas.

    uv run python -m packbuild.india --version 2026.11
    uv run python -m packbuild.india --version 2026.11 \\
        --pincode-boundaries All_India_pincode_Boundary-19312.geojson --pincode-directory pincode.csv

Downloads land once in .cache/packbuild/ (gitignored); the pack is written to --out. data.gov.in
can't be fetched automatically (see the registry notes), so by default the registry's mirror copies
are fetched; a file downloaded by hand from data.gov.in replaces its mirror. State and district
boundaries (--states, --districts) are read only once their source has a registry file, which
needs its licence cleared first (packbuild/sources/nwdp.py).
"""

import argparse
import datetime as dt
import logging
from pathlib import Path

from . import regions_layer
from .fetch import DEFAULT_CACHE, fetch
from .layer import write_pack
from .sources import SOURCES, indiapost, nwdp, url

log = logging.getLogger(__name__)


def build_layers(
    cache_dir,
    refresh=False,
    pincode_boundaries=None,
    pincode_directory=None,
    states=None,
    districts=None,
    regions=None,
):
    """The India layers. Each source is the given file if any, else the registry download. The
    curated regions (`regions` None reads datasets/regions) are unions of PIN code areas: with no
    openly licensed district polygons, a district is the PIN areas the directory files under it."""
    layers = []
    for path, loader in ((states, nwdp.states), (districts, nwdp.districts)):
        if path is not None:
            if nwdp.SOURCE not in SOURCES:
                raise ValueError(
                    f"{nwdp.SOURCE} has no file in the source registry (src/placewise/sources/): "
                    "its licence must be cleared before state and district boundaries go in a pack"
                )
            layers.append(loader(path))
    if pincode_boundaries is None:
        pincode_boundaries = fetch(
            url(indiapost.BOUNDARY_SOURCE, "boundary_mirror"), cache_dir, refresh=refresh
        )
    if pincode_directory is None:
        pincode_directory = fetch(
            url(indiapost.DIRECTORY_SOURCE, "directory_mirror"), cache_dir, refresh=refresh
        )
    pincodes = indiapost.pincodes(pincode_boundaries, pincode_directory)
    layers.append(pincodes)
    layers.append(indiapost.post_offices(pincode_directory))
    curated = regions_layer.for_country(regions, "IN")
    c = pincodes.columns
    regions_layer.check_districts(curated, zip(c["id"], c["state_code"], c["district"], strict=True))
    layers.append(regions_layer.from_features(curated, regions_layer.by_id(pincodes), pincodes.sources))
    return layers


def build_india(cache_dir, out_dir, version, refresh=False, **paths):
    """Build the layers (see build_layers for the optional file paths) and write `<out_dir>/in-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh, **paths)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), "in", version, layers)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.india", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    parser.add_argument("--pincode-boundaries", type=Path, help="All India Pincode Boundary GeoJSON")
    parser.add_argument("--pincode-directory", type=Path, help="All India Pincode Directory CSV")
    parser.add_argument("--states", type=Path, help="state boundaries, WGS84 (needs a cleared licence)")
    parser.add_argument("--districts", type=Path, help="district boundaries, WGS84 (needs a cleared licence)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_india(
        args.cache_dir,
        args.out,
        args.version,
        refresh=args.refresh,
        pincode_boundaries=args.pincode_boundaries,
        pincode_directory=args.pincode_directory,
        states=args.states,
        districts=args.districts,
    )
    print(path)


if __name__ == "__main__":
    main()
