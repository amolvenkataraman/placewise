"""The usa-zip pack: the US ZIP Code Tabulation Areas (`zcta`, built by packbuild.us with their
postal cities), optional beside the usa pack; and the usa pack's `postal_cities`, the few columns of
the ZCTAs its naming rules need when usa-zip isn't installed.

    uv run python -m packbuild.us_zip --version 2026.11   # out/usa-zip-2026.11/

With usa-zip a US lookup has a `postal` code (and search finds ZIP Codes); without it, none. The
locality is the same either way: the naming rules (placewise.engine.naming.usa) let a ZIP Code's
postal city stand for a census-designated place or unincorporated land in a metro county, which
needs the ZCTA a point is in. `postal_cities` keeps those ZCTAs, outlines unchanged, that can
matter: their postal city is a place of the pack, and their box meets the box of a metro county
(widened by POSTAL_MARGIN_DEG, past the naming rules' 1 km shore snap). Outside them a point's
postal city never applies, so leaving the rest out changes no answer (proved on the 2026.11 packs:
packbuild/README.md).
"""

import argparse
import datetime as dt
import logging
from pathlib import Path

import numpy as np

from . import names, us
from .fetch import DEFAULT_CACHE
from .layer import LayerData, write_pack

log = logging.getLogger(__name__)

PACK = "usa-zip"
ABOUT = {"kind": "postal", "covers": ["US"], "requires": ["usa"]}  # pack.json: what it covers, what it needs
LAYER = "postal_cities"
POSTAL_MARGIN_DEG = 0.05  # 5.5 km of latitude, 1.8 km of longitude at 71 N: past the 1 km shore snap
_CHUNK = 2048  # ZCTAs tested against every metro county at once


def _boxes(features):
    """(n, 4) south, west, north, east of each Feature's vertices; a box spanning more than 180
    degrees of longitude (a feature cut at the antimeridian) becomes the whole circle."""
    out = np.empty((len(features), 4))
    for i, f in enumerate(features):
        pts = np.array([p for o in f.outlines for ring in o.rings for p in ring], dtype=np.float64)
        out[i] = pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()
    wide = out[:, 3] - out[:, 1] > 180
    out[wide, 1], out[wide, 3] = -180.0, 180.0
    return out


def postal_cities(zcta, places, counties, cbsa):
    """The `postal_cities` layer from the built `zcta`, `places`, `counties` and `cbsa` LayerData:
    the ZCTAs whose postal city is a place of the pack and whose box meets a metro county's
    (widened), with id, name (the ZIP Code) and postal_place."""
    place_ids = set(places.columns["id"])
    metro_codes = {c for c, t in zip(cbsa.columns["code"], cbsa.columns["type"], strict=True) if t == "metro"}
    metro = [i for i, c in enumerate(counties.columns["cbsa"]) if c in metro_codes]
    county_box = _boxes([counties.features[i] for i in metro])
    county_box += (-POSTAL_MARGIN_DEG, -POSTAL_MARGIN_DEG, POSTAL_MARGIN_DEG, POSTAL_MARGIN_DEG)
    named = [i for i, p in enumerate(zcta.columns["postal_place"]) if p and p in place_ids]
    box = _boxes([zcta.features[i] for i in named])
    meets = np.zeros(len(named), dtype=bool)
    for s in range(0, len(named), _CHUNK):
        b = box[s : s + _CHUNK, None, :]
        meets[s : s + _CHUNK] = (
            (b[..., 0] <= county_box[:, 2]) & (b[..., 2] >= county_box[:, 0])
            & (b[..., 1] <= county_box[:, 3]) & (b[..., 3] >= county_box[:, 1])
        ).any(axis=1)  # fmt: skip
    keep = [i for i, m in zip(named, meets.tolist(), strict=True) if m]
    log.info(
        "postal_cities: %d of %d ZCTAs (%d with a postal city of the pack)",
        len(keep),
        len(zcta.features),
        len(named),
    )
    columns = {c: [zcta.columns[c][i] for i in keep] for c in ("id", "name", "postal_place")}
    postal_source = zcta.columns.get("postal_source", [""] * len(zcta.features))
    from_geonames = any(postal_source[i] == us.postal.GEONAMES for i in keep)
    sources = tuple(s for s in zcta.sources if s != us.GEONAMES or from_geonames)
    return LayerData(
        LAYER, "polygon", columns, sources, features=[zcta.features[i] for i in keep],
        types=dict.fromkeys(columns, "str"),
    )  # fmt: skip


def split(layers):
    """The usa pack's layers (zcta replaced by postal_cities) and the usa-zip pack's ([zcta])."""
    by_name = {layer.name: layer for layer in layers}
    zcta = by_name["zcta"]
    cities = postal_cities(zcta, by_name["places"], by_name["counties"], by_name["cbsa"])
    usa = [cities if layer.name == "zcta" else layer for layer in layers]
    return usa, [zcta]


def build(cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the US layers and write `<out_dir>/usa-zip-<version>/`."""
    _, zips = split(us.build_layers(cache_dir, refresh=refresh))
    return write_pack(Path(out_dir), PACK, version, zips, names=names.for_pack(PACK, zips), about=ABOUT)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.us_zip", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(build(args.cache_dir, args.out, args.version, refresh=args.refresh))


if __name__ == "__main__":
    main()
