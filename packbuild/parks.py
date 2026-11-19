"""The park packs: usa-parks (NPS, USFS, PAD-US 4.1), can-parks (CPCAD), eur-parks (EEA Nationally
designated areas) and world-parks (Wikidata points), read by placewise.engine._within (docs/parks.md).

    uv run python -m packbuild.parks usa --version 2026.11   # out/usa-parks-2026.11/
    uv run python -m packbuild.parks usa-local --version 2026.11   # out/usa-parks-local-2026.11/
    uv run python -m packbuild.parks can eur world --version 2026.11

Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE, $PACKBUILD_CACHE): the
agencies' ArcGIS services are read as query pages (packbuild.sources.parks._rest), the USFS
shapefile, the EEA GeoPackage and the Wikidata query results as files. The packs are written to --out.

Outline packs have one polygon layer per tier (parks_national, parks_state, parks_regional,
parks_local); the US's local parks (PAD-US's city and county parks, most of its rows) are a pack of
their own, usa-parks-local, optional beside usa-parks. eur-parks is optional too, for the countries
its pack.json `covers`. world-parks has one point layer (park_points).
"""

import argparse
import datetime as dt
import logging
from collections import Counter
from pathlib import Path

from . import names
from .fetch import DEFAULT_CACHE, add_keep_downloads, delete_downloads
from .layer import write_pack
from .sources.parks import _common, cpcad, eea, nps, padus, usfs, wikidata

log = logging.getLogger(__name__)

LOCAL_LAYER = _common.LAYER_NAMES[_common.LOCAL]

PACKS = {
    "usa": "usa-parks",
    "usa-local": "usa-parks-local",
    "can": "can-parks",
    "eur": "eur-parks",
    "world": "world-parks",
}
# pack.json coverage for packs whose name doesn't say it all (placewise.store.coverage); eur-parks
# adds the countries it has sites in
ABOUT = {
    "usa-local": {"kind": "parks", "covers": ["US"], "requires": ["usa-parks"]},
    "eur": {"kind": "parks"},
}


def usa_rows(cache_dir, refresh=False):
    """ParkRows for the US: NPS units, national forests, then PAD-US's other parks."""
    rows = nps.parks(nps.fetch(cache_dir, refresh))
    rows += usfs.parks(usfs.fetch(cache_dir, refresh))
    rows += padus.parks(*padus.fetch(cache_dir, refresh))
    return rows


def can_rows(cache_dir, refresh=False):
    return cpcad.parks(cpcad.fetch(cache_dir, refresh))


def eur_rows(cache_dir, refresh=False):
    return eea.parks(eea.fetch(cache_dir, refresh))


ROWS = {"usa": usa_rows, "usa-local": usa_rows, "can": can_rows, "eur": eur_rows}


def build_layers(region, cache_dir, refresh=False):
    """(the layers of one park pack: "usa", "usa-local", "can", "eur" or "world", its pack.json
    coverage fields or None)."""
    if region == "world":
        return [wikidata.park_points(wikidata.fetch(cache_dir, refresh))], None
    rows = ROWS[region](cache_dir, refresh)
    log.info("%s: %d rows, %d parks; by tier %s", region, len(rows), len({r.park for r in rows}),
             dict(sorted(Counter(r.tier for r in rows).items())))  # fmt: skip
    about = ABOUT.get(region)
    if region == "eur":
        about = {**about, "covers": eea.countries(rows)}
    layers = _common.layers(rows)
    if region == "usa":  # city and county parks are usa-parks-local
        return [layer for layer in layers if layer.name != LOCAL_LAYER], about
    if region == "usa-local":
        return [layer for layer in layers if layer.name == LOCAL_LAYER], about
    return layers, about


def build(region, cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the layers and write `<out_dir>/<region>-parks-<version>/`."""
    layers, about = build_layers(region, cache_dir, refresh)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(
        Path(out_dir),
        PACKS[region],
        version,
        layers,
        names=names.for_pack("parks", layers),
        about=about,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.parks", description=__doc__.split("\n")[0])
    parser.add_argument("regions", nargs="+", choices=sorted(PACKS), help="the packs to build")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    add_keep_downloads(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for region in args.regions:
        print(build(region, args.cache_dir, args.out, args.version, refresh=args.refresh))
    delete_downloads(args)  # the raw downloads, once the pack is written


if __name__ == "__main__":
    main()
