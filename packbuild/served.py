"""The city each airport serves: datasets/airports/served.json (CC BY 4.0, curated) -> the world
pack's `airports.served_city` ("geonames:<id>" of a `cities` row), so that a search for an airport
code can answer the city people mean (YYZ -> Toronto, not Mississauga where the airport sits).

OurAirports' `municipality` is the airport's own town, so it is not the city served. The dataset
lists the major airports (every large airport, and the medium ones with scheduled service in India,
the US and Canada); every other airport with an IATA code gets the `CityIndex.nearby` rule: of the
cities of its country within NEARBY_KM, the one with the highest population / (km + GRAVITY_KM)²,
so a big city nearby beats the airport's own town (YYZ -> Toronto) but a sizeable town at the
fence beats a bigger city farther off (OAK -> Oakland, not San Francisco or San Jose).

`check` fails the build, listing every problem, on an id that is not a `cities` row, a city name
that isn't that row's, a country that isn't the city's, a city more than MAX_KM from the airport,
or an airport and city in different countries without notes saying why.
"""

import json
import re

import numpy as np

from placewise.constants._keys import city_key
from placewise.geo.distances import haversine

from . import datasets

DATASET = datasets.path("airports", "served.json")  # in the placewise-data checkout
FIELDS = {"iata", "airport", "city", "country", "geonames", "basis", "notes"}
# curated: checked by hand; geonames: GeoNames lists the code among the city's names; nearby: the
# nearby rule, as the build would apply it
BASES = ("curated", "geonames", "nearby")
MAX_KM = 100.0
NEARBY_KM = 60.0
GRAVITY_KM = 10.0  # the nearby rule ranks cities by population / (km + GRAVITY_KM)²
SOURCE = "placewise-names"
_IATA = re.compile(r"^[A-Z]{3}$")


def load(path=None):
    """Every entry of the dataset, validated, in file order."""
    entries = json.loads((path or DATASET).read_text(encoding="utf-8"))["airports"]
    seen = set()
    for e in entries:
        where = repr(e.get("iata"))
        if extra := set(e) - FIELDS:
            raise ValueError(f"{where}: unknown fields {sorted(extra)}")
        if not _IATA.match(str(e.get("iata", ""))):
            raise ValueError(f"{where}: iata must be three capital letters")
        if e["iata"] in seen:
            raise ValueError(f"{where}: listed twice")
        seen.add(e["iata"])
        if not isinstance(e.get("geonames"), int) or not e.get("city") or not e.get("country"):
            raise ValueError(f"{where}: needs city, country and geonames (the GeoNames id, a number)")
        if e.get("basis") not in BASES:
            raise ValueError(f"{where}: basis must be one of {', '.join(BASES)}")
    return entries


class CityIndex:
    """The `cities` layer by country, for the nearby rule and the checks."""

    def __init__(self, cities):
        c = cities.columns
        self.ids = list(c["id"])
        self.names = list(c["name"])
        self.ascii = list(c["asciiname"])
        self.country = list(c["country"])
        self.lat = np.asarray(cities.lat, dtype=float)
        self.lon = np.asarray(cities.lon, dtype=float)
        self.pop = np.asarray(c["population"], dtype=np.int64)
        self.row = {gid: i for i, gid in enumerate(self.ids)}
        by_country = {}
        for i, code in enumerate(self.country):
            by_country.setdefault(code, []).append(i)
        self.by_country = {code: np.asarray(rows) for code, rows in by_country.items()}

    def km(self, row, lat, lon):
        return float(haversine(lat, lon, self.lat[row], self.lon[row]))

    def nearby(self, lat, lon, country):
        """The row of the city an airport at (lat, lon) serves by the rule, or None."""
        rows = self.by_country.get(country)
        if rows is None:
            return None
        near = np.abs(self.lat[rows] - lat) < NEARBY_KM / 100  # cheap box first (> 1 degree = 111 km)
        rows = rows[near]
        if not len(rows):
            return None
        dist = np.asarray(haversine(lat, lon, self.lat[rows], self.lon[rows]))
        rows, dist = rows[dist <= NEARBY_KM], dist[dist <= NEARBY_KM]
        if not len(rows):
            return None
        score = self.pop[rows] / (dist + GRAVITY_KM) ** 2
        return int(rows[np.argmax(score)])


def check(entries, cities, airports):
    """Raise ValueError listing every entry that doesn't fit the layers (see the module doc)."""
    index = CityIndex(cities) if not isinstance(cities, CityIndex) else cities
    where = {}
    for i, code in enumerate(airports.columns["iata"]):
        if code:
            where.setdefault(code, i)
    lat, lon, countries = list(airports.lat), list(airports.lon), list(airports.columns["country"])
    problems = []
    for e in entries:
        row = index.row.get(f"geonames:{e['geonames']}")
        at = where.get(e["iata"])
        if at is None:
            problems.append(f"{e['iata']}: not an airport of the airports layer")
        elif row is None:
            problems.append(f"{e['iata']}: no city geonames:{e['geonames']}")
        elif city_key(e["city"]) not in (city_key(index.names[row]), city_key(index.ascii[row])):
            problems.append(f"{e['iata']}: {e['city']} is not the name of geonames:{e['geonames']}")
        elif index.country[row] != e["country"]:
            problems.append(f"{e['iata']}: {e['city']} is in {index.country[row]}, not the country given")
        elif (km := index.km(row, lat[at], lon[at])) > MAX_KM:
            problems.append(f"{e['iata']}: {e['city']} is {km:.0f} km away (at most {MAX_KM:.0f} km)")
        elif countries[at] != e["country"] and not e.get("notes"):
            problems.append(f"{e['iata']}: the airport is in {countries[at]}; notes must say why")
    if problems:
        raise ValueError(f"{len(problems)} served.json problems: " + "; ".join(problems))


def add(airports, cities, entries):
    """Add `served_city` to the airports layer in place: the curated city, else the nearby rule
    for airports with an IATA code, else ""; returns how many got one."""
    index = CityIndex(cities)
    check(entries, index, airports)
    curated = {e["iata"]: f"geonames:{e['geonames']}" for e in entries}
    c = airports.columns
    out = []
    for code, country, lat, lon in zip(c["iata"], c["country"], airports.lat, airports.lon, strict=True):
        if code in curated:
            out.append(curated[code])
        elif code:
            row = index.nearby(lat, lon, country)
            out.append("" if row is None else index.ids[row])
        else:
            out.append("")
    c["served_city"] = out
    airports.types["served_city"] = "str"
    if SOURCE not in airports.sources:
        airports.sources = (*airports.sources, SOURCE)
    return sum(1 for v in out if v)
