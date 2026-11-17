"""Metro and vernacular regions: datasets/regions/*.json -> src/placewise/constants/countries/regions.py.

    uv run python -m packbuild.regions            # regenerate the module
    uv run python -m packbuild.regions --check    # exit 1 if the module is out of date

The dataset is the source of truth; the generated module holds what location search needs
offline: each region's id, short name, name, country, admin1 codes, aliases, principal cities and
city aliases. A region with `search_as` (the GTHA, read as the GTA) gets no entry of its own there:
its names become aliases of the region it names. Members, kind and definition are for the country
packs' `regions` layer (packbuild.regions_layer), where every region is drawn on its own.
"""

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

from placewise.constants import countries
from placewise.constants._keys import city_key

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "datasets" / "regions"
MODULE = ROOT / "src" / "placewise" / "constants" / "countries" / "regions.py"
FIELDS = {
    "id",
    "short_name",
    "name",
    "country",
    "admin1",
    "aliases",
    "kind",
    "members",
    "districts",
    "definition",
    "search_as",
    "principal_cities",
    "city_aliases",
    "notes",
}
REQUIRED = {
    "id",
    "short_name",
    "name",
    "country",
    "admin1",
    "aliases",
    "kind",
    "members",
    "definition",
    "notes",
}
# metro: a statistical metro area (OMB MSA or CSA, StatCan CMA); official-planning: an area a public
# body plans or governs as one (ABAG, the NCR Planning Board, Metrolinx, a regional municipality);
# vernacular: a name in common use, drawn with official units
KINDS = ("metro", "official-planning", "vernacular")
_ID = re.compile(r"^region:[a-z0-9]+(?:-[a-z0-9]+)*$")
_MEMBER = re.compile(r"^(?:census|statcan|pin|geonames|iso|ne):[A-Za-z0-9-]+$")
HEADER = '''"""GENERATED from datasets/regions by packbuild.regions; do not edit.

Metro and vernacular regions ("GTA", "SF Bay Area", "NYC", "Delhi NCR"): id, short name, name,
country, admin1 codes, aliases, principal cities with their admin1, and other names of those
cities. Regenerate with `uv run python -m packbuild.regions`.
"""

from ._records import Metro

# fmt: off
REGIONS = (
'''


def load(dataset=DATASET):
    """Every region in the dataset, validated, in file then entry order."""
    regions, ids = [], set()
    for path in sorted(dataset.glob("*.json")):
        for entry in json.loads(path.read_text(encoding="utf-8"))["regions"]:
            _validate(f"{path.name}: {entry.get('id', '?')}", entry, ids)
            regions.append(entry)
    _check_search(regions)
    return regions


def _validate(where, entry, ids):
    if missing := REQUIRED - set(entry):
        raise ValueError(f"{where}: missing {sorted(missing)}")
    if extra := set(entry) - FIELDS:
        raise ValueError(f"{where}: unknown fields {sorted(extra)}")
    if not _ID.match(entry["id"]) or entry["id"] in ids:
        raise ValueError(f"{where}: id must be a new region:<slug>")
    ids.add(entry["id"])
    if entry["kind"] not in KINDS:
        raise ValueError(f"{where}: kind {entry['kind']!r} is not one of {', '.join(KINDS)}")
    _check_definition(where, entry["definition"])
    country = entry["country"]
    if country not in countries.BY_ALPHA2:
        raise ValueError(f"{where}: unknown country {country!r}")
    table = countries.SUBREGIONS.get(country)
    for code in entry["admin1"]:
        if table is not None and code not in table.BY_CODE:
            raise ValueError(f"{where}: unknown admin1 {code!r} for {country}")
    for member in entry["members"]:
        if not _MEMBER.match(member):
            raise ValueError(f"{where}: member {member!r} is not a pack id")
    if len(set(entry["members"])) != len(entry["members"]):
        raise ValueError(f"{where}: a member is listed twice")
    for code, names in entry.get("districts", {}).items():
        if code not in entry["admin1"] or not names:
            raise ValueError(f"{where}: districts of {code!r}: not an admin1 the region reaches, or none")
    cities = entry.get("principal_cities", {})
    for city, code in cities.items():
        if code not in entry["admin1"]:
            raise ValueError(f"{where}: {city} is in {code}, which the region doesn't reach")
    for alias, city in entry.get("city_aliases", {}).items():
        if city not in cities:
            raise ValueError(f"{where}: alias {alias!r} names {city!r}, not a principal city")


def _check_definition(where, definition):
    ok = (
        isinstance(definition, dict)
        and set(definition) == {"title", "url"}
        and bool(definition["title"])
        and urllib.parse.urlparse(str(definition["url"])).scheme == "https"
        and bool(urllib.parse.urlparse(str(definition["url"])).netloc)
    )
    if not ok:
        raise ValueError(f"{where}: definition must be {{title, url}} with an https:// url")


def _check_search(regions):
    """search_as names another region of the same country with its own entry, and every name
    location search reads (folded ones included) means one region."""
    by_id = {r["id"]: r for r in regions}
    names = {}
    for r in regions:
        target = r.get("search_as")
        if target is not None:
            other = by_id.get(target)
            if other is None or other is r or "search_as" in other or other["country"] != r["country"]:
                raise ValueError(f"{r['id']}: search_as must name another region of {r['country']}")
            if r.get("principal_cities") or r.get("city_aliases"):
                raise ValueError(f"{r['id']}: a region read as another lists no cities")
        means = target or r["id"]
        for name in [r["short_name"], r["name"], *r["aliases"], *r.get("city_aliases", {})]:
            k = city_key(name)
            if names.setdefault(k, means) != means:
                raise ValueError(f"{r['id']}: {name!r} also names {names[k]}")


def searchable(regions):
    """The regions location search has an entry for, in order, each with the names of the regions
    read as it (search_as) appended to its aliases."""
    out = {r["id"]: {**r, "aliases": list(r["aliases"])} for r in regions if "search_as" not in r}
    for r in regions:
        if (target := r.get("search_as")) is not None:
            entry = out[target]
            known = {city_key(n) for n in [entry["short_name"], entry["name"], *entry["aliases"]]}
            for name in [r["short_name"], r["name"], *r["aliases"]]:
                if city_key(name) not in known:
                    known.add(city_key(name))
                    entry["aliases"].append(name)
    return list(out.values())


def _items(pairs, indent, width=108):
    lines, line = [], ""
    for item in pairs:
        piece = f"{item},"
        if line and len(" " * indent + line + " " + piece) > width:
            lines.append(" " * indent + line)
            line = piece
        else:
            line = f"{line} {piece}" if line else piece
    if line:
        lines.append(" " * indent + line)
    return "\n".join(lines)


def _q(text):
    return json.dumps(text, ensure_ascii=False)


def render(regions):
    """The generated module's text."""
    out = [HEADER]
    for r in searchable(regions):
        out.append("    Metro(\n")
        out.append(f"        id={_q(r['id'])},\n")
        out.append(f"        key={_q(r['short_name'])}, name={_q(r['name'])}, country={_q(r['country'])},\n")
        out.append(f"        admin1=({''.join(_q(a) + ', ' for a in r['admin1']).rstrip()}),\n")
        if r["aliases"]:
            out.append(f"        aliases=(\n{_items([_q(a) for a in r['aliases']], 12)}\n        ),\n")
        if r.get("city_aliases"):
            pairs = [f"{_q(a)}: {_q(c)}" for a, c in r["city_aliases"].items()]
            out.append(f"        city_aliases={{\n{_items(pairs, 12)}\n        }},\n")
        if r.get("principal_cities"):
            pairs = [f"{_q(c)}: {_q(a)}" for c, a in r["principal_cities"].items()]
            out.append(f"        cities={{\n{_items(pairs, 12)}\n        }},\n")
        out.append("    ),\n")
    out.append(")\n# fmt: on\n")
    return "".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the module is out of date")
    args = parser.parse_args(argv)
    text = render(load())
    if args.check:
        current = MODULE.read_text(encoding="utf-8") if MODULE.exists() else ""
        if current != text:
            print(f"{MODULE} is out of date: run python -m packbuild.regions", file=sys.stderr)
            return 1
        return 0
    MODULE.write_text(text, encoding="utf-8")
    print(f"wrote {MODULE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
