"""The US pack: states, counties, places (incorporated places and CDPs), metro/micro areas (cbsa),
combined statistical areas (csa) and the ZIP Code areas' postal cities (postal_cities: the ZCTAs
themselves are the optional usa-zip pack, packbuild.us_zip), all from the US Census
Bureau (public domain) with GeoNames postal names filling ZIP Codes the Census files lack (CC BY
4.0), the curated regions (Bay Area ...) as unions of counties, and each county's time zone (a `tz`
column from datasets/timezones/usa.json) with the few areas no county fits (the Navajo Nation from
the Census AIANNH areas, the western Aleutians) as the `timezones` layer: packbuild.timezones.

    uv run python -m packbuild.us --version 2026.11

Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE, $PACKBUILD_CACHE);
the pack is written to --out.

Beside the boundaries, the naming rules (placewise.engine.naming.usa) read: every place's
population (SUB-EST for incorporated places, ACS 5-year for CDPs; counties' ACS 5-year population
ranks them in the name index), each CBSA's principal cities
(OMB list 2, largest first) and each ZCTA's postal city (ZIP Code Business Patterns, then
GeoNames), matched to the census place it names.
"""

import argparse
import dataclasses
import datetime as dt
import logging
from pathlib import Path

from . import names, regions_layer, timezones
from .fetch import DEFAULT_CACHE, add_keep_downloads, delete_downloads, fetch, unzip
from .layer import write_pack
from .sources import url, uscensus
from .sources.usa import acs, postal, principal

log = logging.getLogger(__name__)

SHAPEFILES = ("state", "county", "place", "cbsa", "csa", "zcta", "aiannh")
TEXT = ("gazetteer_place", "gazetteer_zcta", "population", "delineation")
DEPTH = ("acs_population", "principal_cities", "zip_cities", "zcta_place")
DOWNLOADS = (*SHAPEFILES, *TEXT, *DEPTH)
GEONAMES, GEONAMES_POSTAL = "geonames", "postal_us"
GEONAMES_CACHE = "geonames-postal"  # export/zip/US.zip, not export/dump/US.zip: its own folder
POPULATION_NULL = uscensus.POPULATION_NULL


def build_layers(cache_dir, refresh=False, regions=None):
    """The US layers, fetching (or reusing) the source files in `cache_dir`: the six Census layers,
    then `regions` (curated regions as unions of counties; `regions` None reads datasets/regions) and
    `timezones` (datasets/timezones/usa.json's shapes; its zones are the counties' `tz` column)."""

    def get(name):
        return fetch(url(uscensus.SOURCE, name), cache_dir, refresh=refresh)

    def shapefile(name):
        archive = get(name)
        return unzip(archive) / f"{archive.stem}.shp"

    def gazetteer(name):
        archive = get(name)
        return uscensus.read_gazetteer(unzip(archive) / f"{archive.stem}.txt")

    def zipped_text(archive):
        return unzip(archive) / f"{archive.stem}.txt"

    delineation = uscensus.read_delineation(get("delineation"))
    population_csv = get("population")
    year = uscensus.population_year(population_csv)
    acs_path = get("acs_population")
    log.info("population estimates: July %d; ACS 5-year to %d", year, acs.vintage(acs_path))
    estimates = acs.read_population(acs_path, (acs.PLACE, acs.ZCTA, acs.COUNTY))
    population = merged_population(
        uscensus.read_population(population_csv),
        f"sub-est{year}",
        estimates[acs.PLACE],
        f"acs5y{acs.vintage(acs_path)}",
    )
    places = uscensus.places(
        shapefile("place"), gazetteer("gazetteer_place"), {g: p for g, (p, _) in population.items()}
    )
    principals = principal.read_principal_cities(get("principal_cities"))
    places = place_columns(places, population, principals)
    layers = [
        uscensus.states(shapefile("state")),
        county_columns(uscensus.counties(shapefile("county"), delineation), estimates[acs.COUNTY]),
        places,
        cbsa_columns(uscensus.cbsa(shapefile("cbsa"), delineation), places, principals),
        uscensus.csa(shapefile("csa"), delineation),
    ]
    # polygons: ZIP lookups are point-in-area questions, which internal points can't answer
    geonames = fetch(url(GEONAMES, GEONAMES_POSTAL), Path(cache_dir) / GEONAMES_CACHE, refresh=refresh)
    cities = postal_inputs(zipped_text(get("zip_cities")), unzip(geonames) / "US.txt", get("zcta_place"))
    zcta = uscensus.zcta(shapefile("zcta"), gazetteer("gazetteer_zcta"))
    layers.append(zcta_columns(zcta, places, estimates[acs.ZCTA], *cities))
    counties = next(layer for layer in layers if layer.name == "counties")
    curated = regions_layer.for_country(regions, "US")
    layers.append(regions_layer.from_features(curated, regions_layer.by_id(counties), counties.sources))
    zoned, shapes = timezones_layer(layers, shapefile("aiannh"))
    zoned = {layer.name: layer for layer in zoned}
    layers = [zoned.get(layer.name, layer) for layer in layers]
    return [*layers, *([shapes] if shapes else [])]


def timezones_layer(layers, aiannh_shp):
    """The counties and states with their `tz` column and the `timezones` layer of usa.json's
    shapes (its Census AIANNH areas read from `aiannh_shp` by AIANNHCE code): ([counties, states],
    shapes)."""
    doc = timezones.load("usa")
    codes = timezones.aiannh_codes(doc)
    areas = (
        {f.properties.get("AIANNHCE"): f for f in uscensus.read_census_shapefile(aiannh_shp)} if codes else {}
    )
    shapes = {sid: areas[code] for sid, code in codes.items() if code in areas}
    states, counties = (next(layer for layer in layers if layer.name == n) for n in ("states", "counties"))
    state_of = dict(zip(states.columns["statefp"], states.columns["id"], strict=True))
    return timezones.country_tables(
        doc, states, [counties], lambda pid, row: state_of.get(row["statefp"]), shapes, (uscensus.SOURCE,)
    )


def merged_population(estimates, estimates_label, survey, survey_label):
    """{GEOID: (population, label)}: the annual estimate where there is one (incorporated places),
    else the ACS 5-year estimate (CDPs)."""
    out = {g: (p, survey_label) for g, p in survey.items()}
    out.update({g: (p, estimates_label) for g, p in estimates.items()})
    return out


def with_columns(layer, columns, types, nulls=None, sources=None):
    """`layer` with extra columns (and their types, nulls, and more sources)."""
    return dataclasses.replace(
        layer,
        columns={**layer.columns, **columns},
        types={**layer.types, **types},
        nulls={**layer.nulls, **(nulls or {})},
        sources=tuple(dict.fromkeys((*layer.sources, *(sources or ())))),
    )


def _geoids(layer):
    return [i.rpartition(":")[2] for i in layer.columns["id"]]


def place_columns(places, population, principals):
    """places + population_source ("sub-est2025", "acs5y2024" or "") and principal (the code of
    the CBSA the place is a principal city of, "" if none)."""
    of = {row["place"]: row["cbsa"] for row in principals}
    geoids = _geoids(places)
    columns = {
        "population_source": [population.get(g, (None, ""))[1] for g in geoids],
        "principal": [of.get(g, "") for g in geoids],
    }
    return with_columns(places, columns, {"population_source": "str", "principal": "str"})


def county_columns(counties, population):
    """counties + population (ACS 5-year, {GEOID: estimate}; null where it has none): the name
    index ranks counties by it, so Clark County means the one in Nevada."""
    columns = {"population": [population.get(g) for g in _geoids(counties)]}
    return with_columns(counties, columns, {"population": "i8"}, {"population": POPULATION_NULL})


def cbsa_columns(cbsa, places, principals):
    """cbsa + principal_cities: comma-separated place ids, largest first (OMB titles a CBSA by its
    largest principal city); principal cities missing from the places layer are left out."""
    population = dict(zip(_geoids(places), places.columns["population"], strict=True))
    order = principal.ordered(principals, population)
    known = set(population)
    columns = {
        "principal_cities": [
            ",".join(f"census:{g}" for g in order.get(code, ()) if g in known)
            for code in cbsa.columns["code"]
        ]
    }
    return with_columns(cbsa, columns, {"principal_cities": "str"})


def postal_inputs(zbp_txt, geonames_txt, relationship_txt):
    return (
        postal.read_zbp(zbp_txt),
        postal.read_geonames_postal(geonames_txt),
        postal.read_zcta_places(relationship_txt),
    )


def zcta_columns(zcta, places, population, zbp, geonames, overlaps):
    """zcta + population (ACS 5-year), postal_city, postal_place (the census place id it names,
    "" if none) and postal_source ("zbp", "geonames" or "")."""
    cols = places.columns
    rows = zip(_geoids(places), cols["name"], cols["state"], cols["class"], cols["population"], strict=True)
    known = [(g, n, s, c == "incorporated", p) for g, n, s, c, p in rows]
    codes = list(zcta.columns["name"])
    found = postal.postal_cities(codes, zbp, geonames, known, overlaps)
    columns = {
        "population": [population.get(c) for c in codes],
        "postal_city": [found[c]["city"] for c in codes],
        "postal_place": [f"census:{found[c]['place']}" if found[c]["place"] else "" for c in codes],
        "postal_source": [found[c]["source"] for c in codes],
    }
    sources = [GEONAMES] if any(s == postal.GEONAMES for s in columns["postal_source"]) else []
    types = {"population": "i8", "postal_city": "str", "postal_place": "str", "postal_source": "str"}
    log.info(
        "zcta: %d of %d with a postal city, %d matched to a place",
        sum(bool(c) for c in columns["postal_city"]), len(codes),
        sum(bool(p) for p in columns["postal_place"]),
    )  # fmt: skip
    return with_columns(zcta, columns, types, {"population": POPULATION_NULL}, sources)


def build_us(cache_dir, out_dir, version, refresh=False, regions=None):
    """Fetch the sources, build the layers and write `<out_dir>/usa-<version>/`."""
    from .us_zip import split  # the ZCTAs go to usa-zip; usa keeps the postal cities it names with

    layers, _ = split(build_layers(cache_dir, refresh=refresh, regions=regions))
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), "usa", version, layers, names=names.for_pack("usa", layers))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.us", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    add_keep_downloads(parser)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_us(args.cache_dir, args.out, args.version, refresh=args.refresh)
    print(path)
    delete_downloads(args)  # the raw downloads, once the pack is written


if __name__ == "__main__":
    main()
