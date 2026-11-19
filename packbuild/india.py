"""The India pack: PIN code areas and post offices (Department of Posts, GODL-India), LGD-keyed
states, districts and cities drawn as unions of PIN areas (Local Government Directory, GODL-India),
neighbourhoods named after post offices, and the curated regions (Delhi NCR ...).

    uv run python -m packbuild.india --version 2026.11
    uv run python -m packbuild.india --version 2026.11 \\
        --pincode-boundaries All_India_pincode_Boundary-19312.geojson --pincode-directory pincode.csv

Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE, $PACKBUILD_CACHE);
the pack is written to --out. data.gov.in can't be fetched automatically (see the registry notes),
so by default the registry's mirror copies are fetched; a file downloaded by hand from data.gov.in
replaces its mirror. State and district boundaries (--states, --districts) are read only once
their source has a registry file, which needs its licence cleared first (packbuild/sources/nwdp.py).

How the derived layers are drawn (packbuild/README.md, India pack):

1. every PIN area gets an LGD district, sub-district and city (packbuild.ind.crosswalk);
2. PIN areas reaching ground a neighbour administers (Natural Earth's de facto countries) are cut
   along it; the pieces there are `india_view_only` (packbuild.ind.defacto);
3. `states`, `districts` and `cities` are exact unions of the pieces (packbuild.ind.layers);
4. `neighbourhoods` are post offices inside cities, named without their type words
   (packbuild.ind.places).
"""

import argparse
import datetime as dt
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import names, regions_layer
from .fetch import DEFAULT_CACHE, add_keep_downloads, delete_downloads, fetch, unzip
from .ind import crosswalk, defacto, lgd, places
from .ind import layers as ind_layers
from .ind import names as ind_names
from .layer import write_pack
from .regions_layer import feature_rings
from .sources import SOURCES, indiapost, naturalearth, nwdp, url

log = logging.getLogger(__name__)
NE_SOURCE = "naturalearth"


def build_layers(
    cache_dir,
    refresh=False,
    pincode_boundaries=None,
    pincode_directory=None,
    states=None,
    districts=None,
    regions=None,
    lgd_tables=None,
    names_dataset=None,
    countries=None,
):
    """The India layers. Each source is the given file if any, else the registry download:
    `lgd_tables` {table: CSV path} (lgd.TABLES), `names_dataset` the curated names file (None:
    datasets/names/ind.json), `countries` Natural Earth's countries as a LayerData (None: read
    from the registry download). `regions` None reads datasets/regions."""
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
    # an office keeps its coordinates only in or near its own PIN area (indiapost.OFFICE_BUFFER_KM)
    offices, _ = indiapost.keep_placed_offices(indiapost.post_offices(pincode_directory), pincodes)
    directory = lgd.read(lgd_tables if lgd_tables is not None else lgd.download(cache_dir, refresh))
    curated_names = ind_names.load(names_dataset)
    curated_names.check(directory)
    if countries is None:
        countries = _countries(cache_dir, refresh)
    d = derive(pincodes, directory, curated_names, countries, indiapost.branch_offices(pincode_directory))
    hoods = places.neighbourhoods(offices, d.city_of_pin, d.city_names, curated_names.not_neighbourhoods)
    layers.extend([*d.layers, d.pincodes, offices, hoods])
    curated = regions_layer.for_country(regions, "IN")
    c = pincodes.columns
    regions_layer.check_districts(curated, zip(c["id"], c["state_code"], c["district"], strict=True))
    check_lgd_units(curated, zip(c["id"], d.crosswalk.district, d.crosswalk.subdistrict, strict=True))
    layers.append(regions_layer.from_features(curated, regions_layer.by_id(pincodes), pincodes.sources))
    return layers


@dataclass(frozen=True)
class Derived:
    """What derive() makes."""

    layers: list  # states, districts, cities
    pincodes: object  # the PIN areas as pieces (LayerData)
    city_of_pin: dict  # pincode -> city id
    city_names: dict  # city id -> (name, *aliases)
    crosswalk: object  # crosswalk.Crosswalk


def derive(pincodes, directory, names, countries, branch_offices=None):
    """The LGD-keyed layers from the pincodes layer, the LGD directory, the curated names, the
    countries and the directory's branch offices per PIN code (module docstring, steps 1-3)."""
    c = pincodes.columns
    rings = [feature_rings([f]) for f in pincodes.features]
    indiapost_districts = list(zip(c["district"], c["state_code"], strict=True))
    cw = crosswalk.build(c["pincode"], rings, indiapost_districts, directory, names, branch_offices)
    for label, rules in (("district", cw.district_rule), ("city", cw.city_rule)):
        log.info("crosswalk %s rules: %s", label, dict(Counter(r or "none" for r in rules)))
    pieces = defacto.pieces(rings, defacto.Neighbours(countries))
    split = len({p.pin for p in pieces if p.view_only})
    log.info("de facto: %d of %d PIN areas reach a neighbour's ground", split, len(rings))
    sources = (*pincodes.sources, lgd.SOURCE, ind_names.SOURCE, NE_SOURCE)
    info = ind_layers.city_info(cw.city, directory, names, _majority(cw.city, cw.district))
    extra = {
        "lgd_district": cw.district,
        "lgd_subdistrict": cw.subdistrict,
        "city": [f"lgd:ulb:{code}" if code else "" for code in cw.city],
    }
    return Derived(
        layers=[
            ind_layers.states_layer(pieces, cw.state, directory, names, sources),
            ind_layers.districts_layer(pieces, cw.district, directory, names, sources),
            ind_layers.cities_layer(pieces, cw.city, info, sources),
        ],
        pincodes=ind_layers.pincodes_layer(
            pincodes, pieces, extra, (*pincodes.sources, lgd.SOURCE, NE_SOURCE)
        ),
        city_of_pin={pin: f"lgd:ulb:{code}" for pin, code in zip(c["pincode"], cw.city, strict=True) if code},
        city_names={f"lgd:ulb:{code}": (i["name"], *i["aliases"]) for code, i in info.items()},
        crosswalk=cw,
    )


def check_lgd_units(regions, pin_rows):
    """For regions with `lgd_units` ("district:<code>", "subdistrict:<code>"): members must be
    exactly the PIN areas the crosswalk puts in those units. `pin_rows` are (pin id, LGD district,
    LGD sub-district) from the crosswalk."""
    by_unit = defaultdict(set)
    for pid, district, sub in pin_rows:
        by_unit[f"district:{district}"].add(pid)
        by_unit[f"subdistrict:{sub}"].add(pid)
    problems = []
    for r in regions:
        if "lgd_units" not in r:
            continue
        want = set()
        for unit in r["lgd_units"]:
            if not by_unit.get(unit):
                problems.append(f"{r['id']}: no PIN area in LGD {unit}")
            want |= by_unit.get(unit, set())
        members = set(r["members"])
        if missing := sorted(want - members):
            problems.append(f"{r['id']}: missing {', '.join(missing)}")
        if extra := sorted(members - want):
            problems.append(f"{r['id']}: members not in its LGD units: {', '.join(extra)}")
    if problems:
        raise ValueError("region LGD units and members disagree:\n  " + "\n  ".join(problems))


def _majority(keys, values):
    per = defaultdict(Counter)
    for k, v in zip(keys, values, strict=True):
        if k and v:
            per[k][v] += 1
    return {k: max(c, key=lambda v, c=c: (c[v], v)) for k, c in per.items()}


def _countries(cache_dir, refresh):
    archive = fetch(url(NE_SOURCE, "countries"), cache_dir, refresh=refresh)
    return naturalearth.countries(unzip(archive) / f"{archive.stem}.shp")


def build_india(cache_dir, out_dir, version, refresh=False, **paths):
    """Build the layers (see build_layers for the optional file paths); write `<out_dir>/ind-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh, **paths)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), "ind", version, layers, names=names.for_pack("ind", layers))


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
    add_keep_downloads(parser)
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
    delete_downloads(args)  # the raw downloads, once the pack is written


if __name__ == "__main__":
    main()
