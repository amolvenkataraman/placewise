"""The park packs: usa-parks (NPS, USFS, PAD-US 4.1), can-parks (CPCAD) and world-parks (Wikidata
points), read by placewise.engine._within (docs/parks.md).

    uv run python -m packbuild.parks usa --version 2026.11   # out/usa-parks-2026.11/
    uv run python -m packbuild.parks can world --version 2026.11

Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE, $PACKBUILD_CACHE): the
agencies' ArcGIS services are read as query pages (packbuild.sources.parks._rest), the USFS
shapefile and the Wikidata query results as files. The packs are written to --out.

Outline packs have one polygon layer per tier (parks_national, parks_state, parks_regional,
parks_local); world-parks has one point layer (park_points).
"""

import argparse
import datetime as dt
import logging
from collections import Counter
from pathlib import Path

from .fetch import DEFAULT_CACHE
from .layer import write_pack
from .sources.parks import _common, cpcad, nps, padus, usfs, wikidata

log = logging.getLogger(__name__)

PACKS = {"usa": "usa-parks", "can": "can-parks", "world": "world-parks"}


def usa_rows(cache_dir, refresh=False):
    """ParkRows for the US: NPS units, national forests, then PAD-US's other parks."""
    rows = nps.parks(nps.fetch(cache_dir, refresh))
    rows += usfs.parks(usfs.fetch(cache_dir, refresh))
    rows += padus.parks(*padus.fetch(cache_dir, refresh))
    return rows


def can_rows(cache_dir, refresh=False):
    return cpcad.parks(cpcad.fetch(cache_dir, refresh))


def build_layers(region, cache_dir, refresh=False):
    """The layers of one park pack ("usa", "can" or "world")."""
    if region == "world":
        return [wikidata.park_points(wikidata.fetch(cache_dir, refresh))]
    rows = usa_rows(cache_dir, refresh) if region == "usa" else can_rows(cache_dir, refresh)
    log.info("%s: %d rows, %d parks; by tier %s", region, len(rows), len({r.park for r in rows}),
             dict(sorted(Counter(r.tier for r in rows).items())))  # fmt: skip
    return _common.layers(rows)


def build(region, cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the layers and write `<out_dir>/<region>-parks-<version>/`."""
    layers = build_layers(region, cache_dir, refresh)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), PACKS[region], version, layers)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.parks", description=__doc__.split("\n")[0])
    parser.add_argument("regions", nargs="+", choices=sorted(PACKS), help="the packs to build")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for region in args.regions:
        print(build(region, args.cache_dir, args.out, args.version, refresh=args.refresh))


if __name__ == "__main__":
    main()
