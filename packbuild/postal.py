"""The world-postal pack: GeoNames' postcode points for the countries outside the country packs
(packbuild.sources.geonames_postal; docs/postal.md), optional beside the world pack.

    uv run python -m packbuild.postal --version 2026.11   # out/world-postal-2026.11/

pack.json says `kind` postal and `covers` the alpha-2 codes of the countries it has points for,
so auto mode fetches it only for those countries (when postal is among data.auto_packs).
"""

import argparse
import dataclasses
import datetime as dt
import logging
from pathlib import Path

from placewise.constants import postal as const
from placewise.constants.store import KIND_POSTAL

from . import names
from .fetch import DEFAULT_CACHE, fetch
from .layer import write_pack
from .sources import geonames_postal as gp
from .sources import url

log = logging.getLogger(__name__)

CACHE_FOLDER = "geonames-postal"  # beside the US postal file (packbuild.us)
DOWNLOAD = "postal_world"
INDEX_ONLY = ("codes",)  # the code and its compact form: only the name index needs them


def build_layers(cache_dir, refresh=False):
    """[postal]: the GeoNames file fetched (or reused) in <cache_dir>/geonames-postal/."""
    archive = fetch(url(gp.SOURCE, DOWNLOAD), Path(cache_dir) / CACHE_FOLDER, refresh=refresh)
    points = gp.points(gp.read_rows(archive))
    layer = gp.postal_layer(points, gp.reaches(points))
    primary = len(layer.columns["id"]) - int(layer.columns["secondary"].sum())
    log.info(
        "postal: %d points, %d codes, %d countries", len(points), primary, len(set(layer.columns["country"]))
    )
    return [layer]


def build(cache_dir, out_dir, version, refresh=False):
    """Fetch the source, build the layer and write `<out_dir>/world-postal-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh)
    about = {"kind": KIND_POSTAL, "covers": sorted(set(layers[0].columns["country"]))}
    index = names.for_pack(const.PACK, layers)
    written = [_without(layer, INDEX_ONLY) for layer in layers]
    return write_pack(Path(out_dir), const.PACK, version, written, names=index, about=about)


def _without(layer, columns):
    """`layer` less `columns` (read by the name index at build time, not by lookups)."""
    keep = {k: v for k, v in layer.columns.items() if k not in columns}
    return dataclasses.replace(layer, columns=keep, types={k: t for k, t in layer.types.items() if k in keep})


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.postal", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the source again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(build(args.cache_dir, args.out, args.version, refresh=args.refresh))


if __name__ == "__main__":
    main()
