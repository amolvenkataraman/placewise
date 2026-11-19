"""The world-notable pack: famous places as points, from Wikidata (CC0) with QRank fame (CC0).

    uv run python -m packbuild.notable --version 2026.11   # out/world-notable-2026.11/

Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE, $PACKBUILD_CACHE):
one QLever query result per kind (notable-<kind>/wikidata) and the pinned QRank file
(qrank/qrank-YYYYMMDD.csv.gz), each with a sidecar, so a rebuild needs no network.

One point layer, `notable`:

| Column | |
|---|---|
| `id` | `wikidata:Q...` |
| `name` | the English label |
| `aliases` | English aliases and short names, `|`-separated, at most 6 (sources/notable/aliases.py) |
| `kind` | constants.notable.KINDS: landmark, university, station, stadium, museum ... |
| `fame` | 0..1, a percentile within the kind (sources/notable/rank.py) |
| `country` | ISO alpha-2 from Wikidata P17 when it names one country, else "": informational only |
| `sitelinks` | Wikipedia and sister-project articles |
| `iata`, `icao`, `ipeds`, `aishe`, `station_code` | external ids where Wikidata has them |
"""

import argparse
import datetime as dt
import logging
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np

from placewise.constants import notable as const

from . import names
from .fetch import DEFAULT_CACHE, add_keep_downloads, delete_downloads
from .layer import LayerData, write_pack
from .sources.notable import aliases, kinds, qrank, rank, wikidata

log = logging.getLogger(__name__)

CODE_COLUMNS = tuple(kinds.CODES)
# airports only for the military: never named, wherever they are
_MILITARY = re.compile(r"\b(air force|air base|airbase|naval air|military|army airfield)\b", re.IGNORECASE)


def usable(item):
    """False for items the pack leaves out: defence aerodromes."""
    return not (item.kind == "airport" and _MILITARY.search(item.name))


def select(items, views):
    """(kept Items in Wikidata id order, their fame): the page-view floor, duplicates, then the
    quotas (sources/notable/rank.py); fame is then recomputed among the kept places."""
    candidates = [i for i in items if usable(i)]
    country = [country_of(i) for i in candidates]
    popular = rank.popular([views.get(i.qid, 0) for i in candidates], country)
    items = [i for i, ok in zip(candidates, popular, strict=True) if ok]
    if not items:
        return [], np.zeros(0)
    lat, lon = np.array([i.lat for i in items]), np.array([i.lon for i in items])
    kind = np.array([i.kind for i in items], dtype=object)
    country = np.array([country_of(i) for i in items], dtype=object)
    raw = rank.raw_fame([views.get(i.qid, 0) for i in items], [i.sitelinks for i in items])
    fame = rank.fame(raw, kind, country)
    dropped = rank.duplicates([i.name for i in items], lat, lon, fame)
    for gone, kept in sorted(dropped.items()):
        target = items[kept]
        target.aliases += [a for a in [items[gone].name, *items[gone].aliases] if a not in target.aliases]
        for column, code in items[gone].codes.items():
            target.codes.setdefault(column, code)
    alive = np.flatnonzero(~np.isin(np.arange(len(items)), list(dropped)))
    keep = alive[rank.quota_keep(lat[alive], lon[alive], kind[alive], country[alive], fame[alive])]
    log.info("notable: %d candidates, %d with enough page views, %d duplicates dropped, %d kept",
             len(candidates), len(items), len(dropped), len(keep))  # fmt: skip
    chosen = sorted(keep.tolist(), key=lambda i: int(items[i].qid[1:]))
    return [items[i] for i in chosen], rank.fame(raw[chosen], kind[chosen], country[chosen])


def country_of(item):
    return next(iter(item.countries)) if len(item.countries) == 1 else ""


def notable_layer(items, fame):
    """The `notable` point layer from the kept Items and their fame."""
    columns = {
        "id": [f"wikidata:{i.qid}" for i in items],
        "name": [i.name for i in items],
        "aliases": [
            "|".join(aliases.clean(i.name, i.aliases, codes=i.codes.values(), kind=i.kind)) for i in items
        ],
        "kind": [i.kind for i in items],
        "fame": np.asarray(fame, dtype=np.float32),
        "country": [country_of(i) for i in items],
        "sitelinks": np.array([min(i.sitelinks, 65535) for i in items], dtype=np.uint16),
    }
    for column in CODE_COLUMNS:
        columns[column] = [i.codes.get(column, "") for i in items]
    lat = np.array([i.lat for i in items], dtype=np.float64)
    lon = np.array([i.lon for i in items], dtype=np.float64)
    return LayerData(const.LAYER, "point", columns, (wikidata.SOURCE, qrank.SOURCE), lat=lat, lon=lon)


def build_layers(cache_dir, refresh=False):
    items = wikidata.read(wikidata.fetch(cache_dir, refresh))
    views = qrank.pageviews(qrank.fetch(cache_dir, refresh), items)
    kept, fame = select(list(items.values()), views)
    layer = notable_layer(kept, fame)
    report(layer)
    return [layer]


def report(layer):
    kinds_count = Counter(layer.columns["kind"])
    countries = Counter(layer.columns["country"])
    log.info("notable by kind: %s", dict(kinds_count.most_common()))
    log.info("notable by country (top 15): %s", dict(countries.most_common(15)))


def build(cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the layer and write `<out_dir>/world-notable-<version>/`."""
    start = time.perf_counter()
    layers = build_layers(cache_dir, refresh)
    path = write_pack(Path(out_dir), const.PACK, version, layers, names=names.for_pack(const.PACK, layers))
    log.info("world-notable: %d places in %.0f s", len(layers[0].columns["id"]), time.perf_counter() - start)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.notable", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    add_keep_downloads(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(build(args.cache_dir, args.out, args.version, refresh=args.refresh))
    delete_downloads(args)  # the raw downloads, once the pack is written


if __name__ == "__main__":
    main()
