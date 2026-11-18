"""COD-AB country packs: OCHA's administrative boundaries (HDX, CC BY 3.0 IGO), one pack per country
named by its lower-case alpha-3 code, one polygon layer per level (`admin1`, `admin2`, ...).

    uv run python -m packbuild.codab lka npl bgd tha --version 2026.11

The countries and how deep each goes are `placewise.constants.codab.COUNTRIES`; each needs an
`ocha-cod-ab-<iso3>` entry in sources/boundaries.json. Only the level shapefiles are downloaded
from the package's zip (packbuild.zipranges), into ~/.placewise/packbuild/ (--cache-dir).

Simplification: Douglas-Peucker at --tolerance-m (default 10 m, as for the Canada pack), each
feature on its own, in a plate carrée centred on the feature (x scaled by the cosine of the
latitude at the middle of its bounding box), so the tolerance is metres on the ground: exact at
that latitude, within about 2% across a unit a few degrees tall. Neighbours' shared borders can
then differ by up to the tolerance.
"""

import argparse
import datetime as dt
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from placewise.constants.codab import COUNTRIES, LAYER_PREFIX
from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.io import read_shapefile

from . import claims, names
from .fetch import DEFAULT_CACHE, fetch, unzip
from .layer import LayerData, write_pack
from .polygons import to_feature
from .sources import naturalearth, ocha, url
from .zipranges import fetch_members

log = logging.getLogger(__name__)

DEFAULT_TOLERANCE_M = 10.0
_R_M = MEAN_RADIUS_KM * 1000.0
COLUMNS = ("id", "name", "pcode", "parent", "type", "valid_on")


@dataclass(frozen=True)
class LocalPlate:
    """Plate carrée in metres about (lat0, lon0): x east, y north, x scaled by cos(lat0)."""

    lat0: float
    lon0: float

    def forward(self, lon, lat):
        k = _R_M * math.radians(1.0)
        return (np.asarray(lon) - self.lon0) * k * math.cos(math.radians(self.lat0)), (
            np.asarray(lat) - self.lat0
        ) * k

    def inverse(self, x, y):
        k = _R_M * math.radians(1.0)
        return np.asarray(x) / (k * math.cos(math.radians(self.lat0))) + self.lon0, np.asarray(
            y
        ) / k + self.lat0


def level_layer(iso3, n, records, tolerance_m=DEFAULT_TOLERANCE_M, cuts=(), sources=()):
    """The `admin<n>` LayerData from (attributes, lon/lat rings) records, simplified, with `cuts`
    ((name, lon/lat ring), packbuild.claims) removed. Several records of one P-code (islands
    written apart) become one feature."""
    rows, rings = {}, {}
    for props, record_rings in records:
        r = ocha.row(props, n)
        if r["id"] in rows and rows[r["id"]]["name"] != r["name"]:
            raise ValueError(f"{iso3} ADM{n}: {r['id']} is both {rows[r['id']]['name']!r} and {r['name']!r}")
        rows.setdefault(r["id"], r)
        rings.setdefault(r["id"], []).extend(record_rings)
    columns = {c: [] for c in COLUMNS}
    features = []
    for fid, r in rows.items():
        feature = simplified(rings[fid], tolerance_m, fid)
        if cuts:
            feature = claims.cut(feature, cuts)
            if feature is None:
                log.warning(
                    "%s ADM%d %s (%s) lies wholly inside a claim cut; left out", iso3, n, fid, r["name"]
                )
                continue
        features.append(feature)
        for c in COLUMNS:
            columns[c].append(r[c])
    if unnamed := columns["name"].count(""):
        log.info("%s ADM%d: %d of %d units have no English name", iso3, n, unnamed, len(features))
    return LayerData(
        f"{LAYER_PREFIX}{n}", "polygon", columns, (ocha.source_id(iso3), *sources), features=features,
        types={c: "str" for c in COLUMNS},
    )  # fmt: skip


def simplified(rings, tolerance_m, fid):
    """A Feature from lon/lat rings, simplified in metres about its own centre."""
    lon = np.concatenate([r[:, 0] for r in rings])
    lat = np.concatenate([r[:, 1] for r in rings])
    plate = LocalPlate(float(lat.min() + lat.max()) / 2, float(lon.min() + lon.max()) / 2)
    projected = [np.column_stack(plate.forward(r[:, 0], r[:, 1])) for r in rings]
    return to_feature(projected, tolerance_m, plate, fid)


def claimant_features(cache_dir, refresh=False):
    """The claimant's polygons from Natural Earth's India point-of-view edition."""
    folder = unzip(fetch(url(naturalearth.SOURCE, "countries_ind"), cache_dir, refresh=refresh))
    shp = next(folder.rglob("*.shp"))
    return [f for f in read_shapefile(shp) if f.properties.get("ADM0_A3") == claims.CLAIMANT]


def build_layers(
    iso3, cache_dir=DEFAULT_CACHE, refresh=False, tolerance_m=DEFAULT_TOLERANCE_M, claimant=None
):
    """The country's admin layers, ADM1 down to its configured depth. `claimant` (features; None
    reads Natural Earth) is only needed where packbuild.claims has sectors for the country."""
    levels = COUNTRIES[iso3].levels
    folder = fetch_members(
        url(ocha.source_id(iso3), "shp"), lambda names: ocha.members(names, iso3, levels), cache_dir, refresh
    )
    names = sorted(p.name for p in folder.iterdir())
    sectors = claims.SECTORS.get(iso3, ())
    cuts, extra = (), ()
    if sectors:
        claimant = claimant_features(cache_dir, refresh) if claimant is None else claimant
        cuts, extra = claims.claim_cuts(claimant, sectors), (naturalearth.SOURCE,)
    layers = []
    for n in range(1, levels + 1):
        stem = ocha.level_stem(names, iso3, n)
        layer = level_layer(iso3, n, ocha.read_level(folder / f"{stem}.shp"), tolerance_m, cuts, extra)
        if sectors and (left := claims.leftover(layer.features, sectors, cuts)):
            raise ValueError(f"{iso3} ADM{n}: claimed ground still inside {left}")
        layers.append(layer)
    return layers


def build(iso3, cache_dir, out_dir, version, refresh=False, tolerance_m=DEFAULT_TOLERANCE_M):
    """Fetch the package, build the layers and write `<out_dir>/<iso3>-<version>/`."""
    if iso3 not in COUNTRIES:
        raise ValueError(f"no COD-AB pack configured for {iso3!r} (placewise.constants.codab.COUNTRIES)")
    layers = build_layers(iso3, cache_dir, refresh=refresh, tolerance_m=tolerance_m)
    for layer in layers:
        vertices = sum(len(r) for f in layer.features for o in f.outlines for r in o.rings)
        log.info("%s/%s: %d features, %d vertices", iso3, layer.name, len(layer.features), vertices)
    return write_pack(Path(out_dir), iso3, version, layers, names=names.for_pack(iso3, layers))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.codab", description=__doc__.split("\n")[0])
    parser.add_argument(
        "countries", nargs="+", choices=sorted(COUNTRIES), metavar="ISO3", help="e.g. lka npl"
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    parser.add_argument(
        "--tolerance-m", type=float, default=DEFAULT_TOLERANCE_M, help="simplification, metres (0: none)"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for iso3 in args.countries:
        print(build(iso3, args.cache_dir, args.out, args.version, args.refresh, args.tolerance_m))


if __name__ == "__main__":
    main()
