"""Alias columns on the world pack's `cities`, `admin1` and `countries` layers: the names people
type for a place beyond its own name, for the name index (forward search).

Sources, best first: the curated dataset (datasets/names/aliases.json, packbuild.aliases), the
India names dataset's former names (datasets/names/ind.json: states, and cities by name), then
GeoNames alternateNamesV2 (CC BY 4.0) filtered by `geonames.pick_alternates`. Each feature keeps at
most CAP of them, none equal to its own name, split into pipe-separated columns by what they are:

| Column | Holds |
|---|---|
| `aliases` | other names: English names, exonyms, nicknames, short forms ("Vegas", "New York") |
| `abbreviations` | abbreviations and short forms in capitals ("NYC", "Ont.", "U.S.") |
| `former_names` | names before a rename ("Bombay", "Orissa", "Zaire"), only curated ones |
| `airport_codes` | IATA codes of the airports serving a city ("YYZ", "YTO"); cities only |

A GeoNames name is dropped when the curated dataset suppresses it ("Ernakulam" is not Kochi) or
when it is the name of another city of the same country (it would hijack that city).
"""

import json

from placewise.constants._keys import city_key

from . import aliases, datasets
from .sources import geonames

COLUMNS = ("aliases", "abbreviations", "former_names", "airport_codes")
CAP = 12  # aliases per feature, all columns together
SOURCE = "placewise-names"
_COLUMN = {
    "code": "airport_codes",
    "abbr": "abbreviations",
    "former": "former_names",
    "name": "aliases",
    "exonym": "aliases",
    "colloquial": "aliases",
}


def _column(name, kind):
    if kind == "short":
        return "aliases" if any(c.islower() for c in name) else "abbreviations"
    return _COLUMN.get(kind)


def curated():
    """(packbuild.aliases.PackAliases, the ind.json document or {}) from the curated datasets."""
    india = datasets.path("names", "ind.json")
    return aliases.for_packs(aliases.load()), json.loads(
        india.read_text(encoding="utf-8")
    ) if india.exists() else {}


def columns(rows, cap=CAP):
    """{column: [pipe-joined names]} for rows of (own names, [(name, kind)] best first, keys to
    drop). Names are compared by `city_key`; the first of a key wins."""
    out = {c: [] for c in COLUMNS}
    for own, pairs, dropped in rows:
        seen = {city_key(n) for n in own if n} | set(dropped)
        kept = {c: [] for c in COLUMNS}
        count = 0
        for name, kind in pairs:
            k, column = city_key(name), _column(name, kind)
            if count >= cap or not k or k in seen or column is None:
                continue
            seen.add(k)
            kept[column].append(name)
            count += 1
        for c in COLUMNS:
            out[c].append("|".join(kept[c]))
    return out


def _gid(value):
    return int(value.split(":", 1)[1]) if value and value.startswith("geonames:") else None


def _india_formers(india):
    """{current name key: [former names]} of India's states and cities (datasets/names/ind.json)."""
    out = {}
    states = [u for u in india.get("units", ()) if str(u.get("lgd", "")).startswith("state:")]
    for entry in [*states, *india.get("cities", ())]:  # cities' "lgd" lists the local bodies
        for former in entry.get("former") or ():
            out.setdefault(city_key(entry["name"]), []).append(former["name"])
    return out


def add(cities, admin1, countries, alternates_path, country_ids, curated, india=None):
    """Add COLUMNS to the three layers in place; `country_ids` is {alpha-2: GeoNames id}
    (countryInfo), `curated` a packbuild.aliases.PackAliases, `india` the ind.json document.
    Returns {layer name: features with at least one alias}."""
    india_formers = _india_formers(india or {})
    city_ids = [_gid(v) for v in cities.columns["id"]]
    admin1_ids = [_gid(v) for v in admin1.columns.get("geonames", [""] * len(admin1.columns["id"]))]
    iso2 = list(countries.columns["iso2"])
    country_gids = [country_ids.get(c) for c in iso2]
    wanted = {g for g in [*city_ids, *admin1_ids, *country_gids] if g}
    alternates = geonames.read_alternate_names(alternates_path, wanted)

    biggest = {}  # (name key, country) -> population of the biggest city of that name
    for name, country, pop in zip(
        cities.columns["name"], cities.columns["country"], cities.columns["population"], strict=True
    ):
        k = (city_key(name), country)
        biggest[k] = max(biggest.get(k, -1), int(pop))

    rows = []
    for gid, name, ascii_name, country, pop in zip(
        city_ids,
        cities.columns["name"],
        cities.columns["asciiname"],
        cities.columns["country"],
        cities.columns["population"],
        strict=True,
    ):
        own = (name, ascii_name)
        mine = list(curated.cities.get(gid, ()))
        if country == "IN":
            mine += [(f, "former") for f in india_formers.get(city_key(name), ())]
        formers = {city_key(n) for n, k in mine if k == "former"}
        found = geonames.pick_alternates(alternates.get(gid, ()), population=int(pop), formers=formers)
        others = {city_key(n) for n in own}
        found = [
            (n, k)
            for n, k in found
            if k == "code" or city_key(n) in others or (city_key(n), country) not in biggest
        ]
        rows.append((own, mine + found, curated.suppressed.get(gid, set())))
    counts = {"cities": _set(cities, columns(rows))}

    rows = []
    for gid, name, country in zip(admin1_ids, admin1.columns["name"], admin1.columns["country"], strict=True):
        mine = [(f, "former") for f in india_formers.get(city_key(name), ())] if country == "IN" else []
        formers = {city_key(n) for n, _ in mine}
        found = geonames.pick_alternates(
            alternates.get(gid, ()), population=geonames.HISTORIC_MIN_POPULATION, formers=formers, codes=False
        )
        rows.append(((name,), mine + found, curated.suppressed.get(gid, set())))
    counts["admin1"] = _set(admin1, columns(rows))

    rows = []
    for gid, name, code in zip(country_gids, countries.columns["name"], iso2, strict=True):
        mine = list(curated.countries.get(code, ()))
        formers = {city_key(n) for n, k in mine if k == "former"}
        found = geonames.pick_alternates(
            alternates.get(gid, ()), population=geonames.HISTORIC_MIN_POPULATION, formers=formers, codes=False
        )
        rows.append(((name,), mine + found, set()))
    counts["countries"] = _set(countries, columns(rows))
    return counts


def _set(layer, cols):
    for c, values in cols.items():
        layer.columns[c] = values
        layer.types[c] = "str"
    if SOURCE not in layer.sources:
        layer.sources = (*layer.sources, SOURCE)
    return sum(any(cols[c][i] for c in COLUMNS) for i in range(len(cols["aliases"])))
