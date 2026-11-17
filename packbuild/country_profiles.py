"""The world pack's `country_facts` layer: one point per country with its profile facts, from
GeoNames, Unicode CLDR and Wikidata. `packbuild.world` adds it to the world pack.

- GeoNames countryInfo.txt: capital, area, population, top-level domain, calling code, postal
  code format and pattern, languages, neighbours; timeZones.txt: IANA time zones; cities1000: the
  capital's coordinates (the point), else Natural Earth's label point.
- CLDR (cldr-json, the release pinned in the registry): currency (the territory's first current
  tender in currencyData, an ISO 4217 code) with its English name and symbols, measurement system,
  first day of the week, and the short date pattern of the territory's likely locale.
- Wikidata: driving side.
- The continent is the package's own (constants.countries.groups, from datasets/country_groups),
  so profiles agree with `placewise.world.countries(continent=...)`.

Every value comes from a source; where the sources have none (or disagree) it is null. A country
with neither a capital in GeoNames nor a Natural Earth label point has no point, so no row.
Download URLs are in the source registry (src/placewise/sources/countries.json).
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from placewise.constants.world import FACTS_LAYER

from .fetch import DEFAULT_CACHE, fetch
from .layer import LayerData
from .sources import cldr, geonames, url, wikidata
from .sources.geonames import GEONAME_FIELDS, read_tsv

log = logging.getLogger(__name__)

MEASUREMENT = {"metric": "metric", "US": "US", "UK": "imperial-mixed"}  # CLDR system -> profile value
DAYS = {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday", "fri": "friday"}
DAYS |= {"sat": "saturday", "sun": "sunday"}
NULL = -1  # integer null (population, population_year)
INTEGERS = {"population": "i8", "population_year": "i2"}
_F = {name: i for i, name in enumerate(GEONAME_FIELDS)}


@dataclass(frozen=True)
class Inputs:
    """The downloaded files a build reads, and the CLDR release they come from."""

    country_info: Path
    time_zones: Path
    measurement: Path
    week: Path
    likely: Path
    available: Path
    currency_data: Path
    currencies: Path
    driving_side: Path
    cldr_version: str
    dates: dict = field(default_factory=dict)  # CLDR locale -> its ca-gregorian.json


# --- fetching ---


def _offline(link, cache_dir):
    path = Path(cache_dir) / Path(link.split("?", 1)[0]).name
    if not (path.exists() and path.with_name(path.name + ".json").exists()):
        raise FileNotFoundError(path)
    return path


def inputs(cache_dir=DEFAULT_CACHE, refresh=False, offline=False, fetcher=None):
    """Every input file, downloaded once into `cache_dir` (`offline`: FileNotFoundError for a file
    not cached yet). `fetcher(url, cache_dir, refresh=...)` defaults to packbuild.fetch.fetch."""
    cache_dir = Path(cache_dir)
    fetcher = fetcher or fetch
    version = re.search(r"/cldr-json/([^/]+)/", url("cldr", "dates")).group(1)
    core = cache_dir / f"cldr-{version}"

    def get(link, where):
        return _offline(link, where) if offline else fetcher(link, where, refresh=refresh)

    found = Inputs(
        country_info=get(url("geonames", "country_info"), cache_dir),
        time_zones=get(url("geonames", "time_zones"), cache_dir),
        measurement=get(url("cldr", "measurement_data"), core),
        week=get(url("cldr", "week_data"), core),
        likely=get(url("cldr", "likely_subtags"), core),
        available=get(url("cldr", "available_locales"), core),
        currency_data=get(url("cldr", "currency_data"), core),
        currencies=get(url("cldr", "currencies_en"), core / "en"),
        driving_side=get(url("wikidata", "driving_side"), cache_dir / "wikidata"),
        cldr_version=version,
    )
    likely, available = cldr.likely_subtags(found.likely), cldr.available_locales(found.available)
    for code in _countries():
        locale = cldr.territory_locale(code, likely, available)
        if locale and locale not in found.dates:
            link = f"{url('cldr', 'dates')}{locale}/ca-gregorian.json"
            found.dates[locale] = get(link, core / "dates" / locale)
    return found


def cached(cache_dir=DEFAULT_CACHE):
    """Are all the inputs already downloaded?"""
    try:
        inputs(cache_dir, offline=True)
    except FileNotFoundError:
        return False
    return True


# --- facts ---


def _countries():
    from placewise.constants.countries import BY_ALPHA2

    return tuple(sorted(BY_ALPHA2))


def _continents():
    from placewise.constants.countries import groups

    return {
        code: group["name"]
        for group in groups.GEOGRAPHIC.values()
        if group["kind"] == "continent"
        for code in group["members"]
    }


def _number(text):
    if not text:
        return None
    value = float(text)
    return int(value) if value.is_integer() and "." not in text else value


def _phone(text):
    """GeoNames' calling code ("1", "+1-268", "+1-809 and 1-829") as "+1", "+1-268", "+1-809, +1-829"."""
    if not text:
        return None
    parts = (part.strip() for part in re.split(r"\s+and\s+|,", text))
    return ", ".join("+" + part.lstrip("+") for part in parts if part)


def _split(text):
    return tuple(part.strip() for part in text.split(",") if part.strip()) if text else ()


def build(found, countries=None):
    """{alpha-2: {fact: value}} for `countries` (default: every ISO 3166-1 code); None (or () for
    lists) where the sources have nothing."""
    from placewise.constants.countries import BY_ALPHA2

    facts = geonames.read_country_facts(found.country_info)
    zones = geonames.read_time_zones(found.time_zones)
    systems, first = cldr.measurement_systems(found.measurement), cldr.first_days(found.week)
    likely, available = cldr.likely_subtags(found.likely), cldr.available_locales(found.available)
    tender, names = cldr.current_currencies(found.currency_data), cldr.currencies(found.currencies)
    sides, continents = wikidata.driving_sides(found.driving_side), _continents()
    out = {}
    for code in countries or _countries():
        row = facts.get(code, {})
        locale = cldr.territory_locale(code, likely, available)
        currency = tender.get(code)
        name, symbol, narrow = names.get(currency, (None, None, None))
        out[code] = {
            "name": BY_ALPHA2[code].name,
            "iso3": BY_ALPHA2[code].alpha3,
            "capital": row.get("capital") or None,
            "continent": continents.get(code),
            "currency": currency,
            "currency_name": name,
            "currency_symbol": symbol,
            "currency_narrow_symbol": narrow,
            "calling_code": _phone(row.get("phone")),
            "languages": _split(row.get("languages")),
            "measurement_system": MEASUREMENT[systems.get(code, systems[cldr.WORLD])],
            "driving_side": sides.get(code),
            "first_day_of_week": DAYS[first.get(code, first[cldr.WORLD])],
            "locale": locale,
            "date_format": cldr.short_date(found.dates[locale], locale) if locale else None,
            "tld": row.get("tld") or None,
            "time_zones": zones.get(code, ()),
            "population": _number(row.get("population")),
            "population_year": None,  # countryInfo gives no reference year
            "area_km2": _number(row.get("area")),
            "neighbours": _split(row.get("neighbours")),
            "postal_code_format": row.get("postal_code_format") or None,
            "postal_code_regex": row.get("postal_code_regex") or None,
        }
    return out


def capitals(cities_path, facts):
    """{alpha-2: (lat, lon)} of each country's capital: its GeoNames PPLC city, the one named as
    in countryInfo when there are several, else the most populous."""
    best = {}
    for row in read_tsv(cities_path, len(GEONAME_FIELDS)):
        if row[_F["feature_code"]] != "PPLC":
            continue
        code = row[_F["country_code"]]
        wanted = (facts.get(code) or {}).get("capital")
        rank = (wanted in (row[_F["name"]], row[_F["asciiname"]]), int(row[_F["population"]] or 0))
        if code not in best or rank > best[code][0]:
            best[code] = (rank, (float(row[_F["latitude"]]), float(row[_F["longitude"]])))
    return {code: point for code, (_, point) in best.items()}


# --- the layer ---


def _column(name, values):
    if name in INTEGERS:
        return [NULL if v is None else v for v in values]
    if name == "area_km2":
        return [float("nan") if v is None else float(v) for v in values]
    return [",".join(v) if isinstance(v, tuple) else v for v in values]


def layer(built, capital_points, label_points=None):
    """The country_facts point layer: lists comma-joined, integer nulls -1, area NaN when unknown.
    The point is the capital where known, else the label point; countries with neither are left
    out (logged). `point` says which."""
    label_points = label_points or {}
    kept, lat, lon, point = [], [], [], []
    for code in built:
        kind, where = ("capital", capital_points[code]) if code in capital_points else ("label", None)
        where = where or label_points.get(code)
        if where is None:
            log.warning("%s: no capital or label point for %s; left out", FACTS_LAYER, code)
            continue
        kept.append(code)
        point.append(kind)
        lat.append(where[0])
        lon.append(where[1])
    names = list(next(iter(built.values()))) if built else []
    columns = {"id": [f"iso:{code}" for code in kept], "iso2": kept}
    columns |= {name: _column(name, [built[code][name] for code in kept]) for name in names}
    columns["point"] = point
    types = {name: "str" for name in columns} | INTEGERS | {"area_km2": "f8"}
    sources = ("geonames", "cldr", "wikidata") + (("naturalearth",) if "label" in point else ())
    return LayerData(
        FACTS_LAYER,
        "point",
        columns,
        sources,
        lat=np.asarray(lat, dtype=np.float64),
        lon=np.asarray(lon, dtype=np.float64),
        types=types,
        nulls=dict.fromkeys(INTEGERS, NULL),
    )


def country_facts(cache_dir, cities_path, countries_shp=None, refresh=False, fetcher=None):
    """The country_facts layer, fetching (or reusing) its inputs in `cache_dir`; `countries_shp`
    (Natural Earth admin-0) gives label points for countries without a capital."""
    from .sources import naturalearth

    found = inputs(cache_dir, refresh=refresh, fetcher=fetcher)
    built = build(found)
    labels = naturalearth.label_points(countries_shp) if countries_shp else {}
    return layer(built, capitals(cities_path, geonames.read_country_facts(found.country_info)), labels)
