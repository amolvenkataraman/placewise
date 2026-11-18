"""Cities and city aliases for offline location search.

    uv run python -m packbuild.cities            # regenerate both
    uv run python -m packbuild.cities --check    # exit 1 if either is out of date

- `src/placewise/constants/countries/<alpha3>/cities.py` for the countries with an admin1 table
  (usa, can, ind, gbr): GeoNames cities1000 (CC BY 4.0) places with POPULATION_MIN people or more,
  plus every admin1 seat and capital, with the admin1 as its ISO 3166-2 suffix.
- `src/placewise/constants/countries/city_aliases.py` from `datasets/names/aliases.json`
  (packbuild.aliases); every alias must name its GeoNames city, in the stated country and admin1.

Downloads are cached in ~/.placewise/packbuild/ (see packbuild.fetch).
"""

import argparse
import json
import sys
from pathlib import Path

from placewise.constants import countries

from . import aliases, regions
from .fetch import DEFAULT_CACHE, fetch, unzip
from .sources import url
from .sources.geonames import GEONAME_FIELDS, read_admin1, read_tsv

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "placewise" / "constants" / "countries"
POPULATION_MIN = 100_000
SEATS = {"PPLA", "PPLC"}  # admin1 seats and national capitals
FOLDERS = {"US": "usa", "CA": "can", "IN": "ind", "GB": "gbr"}
_F = {name: i for i, name in enumerate(GEONAME_FIELDS)}


def sources(cache_dir=DEFAULT_CACHE, refresh=False):
    """(cities1000.txt, admin1CodesASCII.txt), downloading them once."""
    archive = fetch(url("geonames", "cities"), cache_dir, refresh)
    return unzip(archive) / "cities1000.txt", fetch(url("geonames", "admin1_codes"), cache_dir, refresh)


def _admin1(country, geonames_code, admin1_names):
    """GeoNames' admin1 code ("CA.08") as the ISO 3166-2 suffix ("ON")."""
    if country in ("US", "GB"):
        return geonames_code  # GeoNames uses USPS codes and ENG / SCT / WLS / NIR
    name = admin1_names.get(f"{country}.{geonames_code}")
    code = countries.SUBREGIONS[country].lookup(name) if name else None
    if code is None:
        raise ValueError(f"no ISO code for GeoNames admin1 {country}.{geonames_code} ({name})")
    return code


def read_cities(cities_path, admin1_path):
    """{alpha-2: [(name, admin1, population, alternate names)]} for the countries in FOLDERS, the
    most populous first, keeping places with POPULATION_MIN people or more and every seat."""
    admin1_names = read_admin1(admin1_path)
    found = {cc: [] for cc in FOLDERS}
    for row in read_tsv(cities_path, len(GEONAME_FIELDS)):
        country = row[_F["country_code"]]
        if country not in found or not row[_F["admin1_code"]]:
            continue
        population = int(row[_F["population"]] or 0)
        if population < POPULATION_MIN and row[_F["feature_code"]] not in SEATS:
            continue
        admin1 = _admin1(country, row[_F["admin1_code"]], admin1_names)
        names = {row[_F["name"]], row[_F["asciiname"]], *row[_F["alternatenames"]].split(",")}
        found[country].append((row[_F["name"]], admin1, population, names))
    for rows in found.values():
        rows.sort(key=lambda r: (-r[2], r[0]))
    return found


def _wrap(items, indent=4, width=108):
    lines, line = [], ""
    for item in items:
        if line and len(" " * indent + line + " " + item) > width:
            lines.append(" " * indent + line)
            line = item
        else:
            line = f"{line} {item}" if line else item
    if line:
        lines.append(" " * indent + line)
    return "\n".join(lines)


def render_cities(country, rows):
    """The generated cities module for one country."""
    name = countries.BY_ALPHA2[country].name
    items = [f"({json.dumps(n, ensure_ascii=False)}, {json.dumps(a)}, {p})," for n, a, p, _ in rows]
    return f'''"""GENERATED from GeoNames cities1000 (CC BY 4.0) by packbuild.cities; do not edit.

Cities of {name} with {POPULATION_MIN:,} people or more, plus every admin1 seat and the capital:
(name, admin1 ISO 3166-2 suffix, population), the most populous first. Location search uses them to
tell which reading of a code a named city fits ("Toronto, CA"); they don't place bare city names.
"""

# fmt: off
CITIES = (
{_wrap(items)}
)
# fmt: on
'''


def outputs(cities_path=None, admin1_path=None):
    """{path: text} for every generated module; cities only when the GeoNames files are given."""
    entries = aliases.load()
    aliases.check_regions(entries, regions.load())
    out = {PACKAGE / "city_aliases.py": aliases.render(entries)}
    if cities_path is not None:
        aliases.check_targets(entries, cities_path, admin1_path)
        for country, rows in read_cities(cities_path, admin1_path).items():
            out[PACKAGE / FOLDERS[country] / "cities.py"] = render_cities(country, rows)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if a module is out of date")
    parser.add_argument("--refresh", action="store_true", help="download the GeoNames files again")
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs(*sources(refresh=args.refresh)).items():
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current == text:
            continue
        if args.check:
            stale.append(path)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("out of date (run python -m packbuild.cities): " + ", ".join(map(str, stale)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
