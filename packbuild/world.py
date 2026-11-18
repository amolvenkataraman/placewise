"""The world pack: countries and admin-1 polygons (Natural Earth), cities (GeoNames), airports
(OurAirports, with the city each one serves: packbuild.served), the names people type for cities,
admin-1 units and countries (alias columns: packbuild.world_aliases, from datasets/names and
GeoNames alternate names), country facts (GeoNames, Unicode CLDR, Wikidata:
packbuild.country_profiles) and time-zone polygons (datasets/timezones/world.json drawn with the
Natural Earth units: packbuild.timezones). Natural Earth's disputed areas are the `worldviews` layer.

    uv run python -m packbuild.world --version 2026.11

Downloads land once in ~/.placewise/packbuild/ (packbuild.fetch.DEFAULT_CACHE, $PACKBUILD_CACHE);
the pack is written to --out.
"""

import argparse
import dataclasses
import datetime as dt
import logging
from collections import Counter
from pathlib import Path

from placewise.constants._keys import city_key
from placewise.constants.lookup import CITY_EXCLUDED_FEATURE_CODES

from . import country_profiles, names, served, timezones, world_aliases
from .fetch import DEFAULT_CACHE, fetch, unzip
from .layer import write_pack
from .sources import geonames, naturalearth, ourairports, url
from .sources.geonames import read_tsv

log = logging.getLogger(__name__)


def build_layers(cache_dir, refresh=False):
    """The six world layers, fetching (or reusing) the source files in `cache_dir`."""

    def get(url):
        return fetch(url, cache_dir, refresh=refresh)

    def shapefile(url):
        archive = get(url)
        return unzip(archive) / f"{archive.stem}.shp"

    countries_shp = shapefile(url("naturalearth", "countries"))
    countries = naturalearth.countries(countries_shp)
    admin1 = naturalearth.admin1(shapefile(url("naturalearth", "admin1")))
    worldviews = naturalearth.disputed_areas(shapefile(url("naturalearth", "disputed_areas")))
    cities_zip = get(url("geonames", "cities"))
    cities_txt = unzip(cities_zip) / f"{cities_zip.stem}.txt"
    country_info = get(url("geonames", "country_info"))
    admin1_codes = get(url("geonames", "admin1_codes"))
    cities = geonames.cities(cities_txt, admin1_codes, country_info)
    admin1 = admin1_population(admin1, cities, admin1_codes)
    country_ids = {
        code: int(facts["geonameid"])
        for code, facts in geonames.read_country_facts(country_info).items()
        if facts["geonameid"].isdigit()
    }
    counts = world_aliases.add(
        cities,
        admin1,
        countries,
        get(url("geonames", "alternate_names")),
        country_ids,
        *world_aliases.curated(),
    )
    log.info("features with aliases: %s", counts)
    airports = ourairports.airports(get(url("ourairports", "airports")))
    log.info("airports with a served city: %d", served.add(airports, cities, served.load()))
    facts = country_profiles.country_facts(
        cache_dir,
        cities_txt,
        countries_shp,
        refresh=refresh,
        fetcher=lambda u, d, refresh: fetch(u, d, refresh),
    )
    zones = timezones.world_layer(timezones.load("world"), countries, admin1)
    return [countries, admin1, worldviews, cities, airports, facts, zones]


def admin1_population(admin1, cities, admin1_codes_path):
    """admin1 + population: the people of the GeoNames cities in each unit (sections of a city,
    already counted in it, left out), joined by the unit's GeoNames id through admin1CodesASCII;
    null where no city is known. The name index ranks admin-1 units by it, so a small parish
    named Portland doesn't come before Portland, Oregon."""
    code_of = {}
    for row in read_tsv(admin1_codes_path, 4, exact=False):
        code, name, ascii_name, geonameid = row[:4]
        country = code.partition(".")[0]
        code_of[f"geonames:{geonameid}"] = code
        for text in (name, ascii_name):
            code_of.setdefault((country, city_key(text)), code)
    cols = cities.columns
    people = Counter()
    rows = zip(cols["country"], cols["admin1"], cols["feature_code"], cols["population"], strict=True)
    for country, code, feature, population in rows:
        if feature not in CITY_EXCLUDED_FEATURE_CODES and population and population > 0:
            people[f"{country}.{code}"] += int(population)
    a1 = admin1.columns
    keys = zip(a1["geonames"], a1["country"], a1["name"], strict=True)
    codes = [code_of.get(g) or code_of.get((c, city_key(n))) for g, c, n in keys]
    population = [people.get(code, 0) or None for code in codes]
    log.info(
        "admin1 with a population from their cities: %d of %d",
        sum(p is not None for p in population),
        len(population),
    )
    return dataclasses.replace(
        admin1,
        columns={**admin1.columns, "population": population},
        types={**admin1.types, "population": "i8"},
        nulls={**admin1.nulls, "population": -1},
    )


def build_world(cache_dir, out_dir, version, refresh=False):
    """Fetch the sources, build the layers and write `<out_dir>/world-<version>/`."""
    layers = build_layers(cache_dir, refresh=refresh)
    for layer in layers:
        log.info("%s: %d features", layer.name, len(layer.columns["id"]))
    return write_pack(Path(out_dir), "world", version, layers, names=names.for_pack("world", layers))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m packbuild.world", description=__doc__.split("\n")[0])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE, help="download cache")
    parser.add_argument("--out", type=Path, default=DEFAULT_CACHE / "out", help="output directory")
    parser.add_argument("--version", default=dt.date.today().strftime("%Y.%m"), help="CalVer, e.g. 2026.11")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = build_world(args.cache_dir, args.out, args.version, refresh=args.refresh)
    print(path)


if __name__ == "__main__":
    main()
