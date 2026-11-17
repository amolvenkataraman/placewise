"""Location-search benchmark (not collected by pytest):

    uv run python tests/text/bench_text.py [N] [--dump FILE]

A corpus of N realistic location strings (default 20,000): every string the tests in tests/text
read, plus strings built from the public reference tables (cities, states, provinces, countries,
metros) in the forms listings write them. Prints the import time, the first-call latency (the
lookup tables are built lazily), throughput over unique strings and over repeats, the memory the
tables take, and a digest of every result; `--dump` writes the results, one per line, for diffing.
Times are CPU time (time.process_time), so other work on the machine skews them less.
"""

import ast
import hashlib
import random
import resource
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = (
    "{city}, {code}",
    "{city}, {code}, {country}",
    "{city} {code}",
    "{city}, {state}",
    "Remote - {country}",
    "Hybrid - {city}, {code}",
    "{city}, {code} or Remote",
    "Remote ({country})",
    "{city}, {code}; {city2}, {code2}",
    "{country}, {code}, {city}",
    "{city} Office - {state}",
    "On-site in {city}, {code} (3 days/week)",
    "{city}, {code} {postal}",
    "Greater {city} Area",
    "{metro}",
    "Remote in {metro}",
    "{city}",
    "{state}",
    "{code}-Remote",
    "{city}, {code} + 3 more",
    "US | {state} | {city}",
    "{city} / {city2}",
)
POSTAL = {"US": "94105", "CA": "M5V 2T6", "IN": "560001", "GB": ""}


def test_strings():
    """Every string literal in the location-search tests that could be a location."""
    found = []
    for path in sorted(HERE.rglob("test_*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and 0 < len(node.value) <= 120:
                found.append(node.value)
    return list(dict.fromkeys(found))


def synthetic(n, seed=0):
    from placewise.constants import countries

    rng = random.Random(seed)
    cities = [(name, code, cc) for cc, rows in countries.CITIES.items() for name, code, _ in rows[:400]]
    names = {cc: countries.BY_ALPHA2[cc].name for cc in countries.SUBREGIONS}
    states = {(cc, s.code): s.name for cc, table in countries.SUBREGIONS.items() for s in table.SUBREGIONS}
    metros = [m.name for m in countries.METROS] + [m.key for m in countries.METROS]
    other = [c.name for c in countries.COUNTRIES]
    out = []
    while len(out) < n:
        city, code, cc = rng.choice(cities)
        city2, code2, _ = rng.choice(cities)
        country = names[cc] if rng.random() < 0.8 else rng.choice(other)
        out.append(
            rng.choice(TEMPLATES).format(
                city=city,
                code=code,
                country=country,
                state=states.get((cc, code), code),
                city2=city2,
                code2=code2,
                postal=POSTAL[cc],
                metro=rng.choice(metros),
            )
        )
    return out


def corpus(n):
    base = test_strings()
    return base + synthetic(max(0, n - len(base)))


class BenchGazetteer:
    """Knows the reference cities, the way a data pack would; records every question."""

    def __init__(self):
        from placewise.constants import countries
        from placewise.model.places import Place, PlaceKind

        self.calls = []
        self.places = {}
        for cc, rows in countries.CITIES.items():
            for name, code, _ in rows:
                place = Place(
                    id=f"bench:{cc}-{code}-{name}",
                    name=name,
                    kind=PlaceKind.LOCALITY,
                    codes={"iso2": cc, "admin1": code},
                )
                for k in ((name.lower(), cc, code), (name.lower(), cc, None), (name.lower(), None, None)):
                    self.places.setdefault(k, place)

    def match(self, city, country_iso2, admin1_code):
        self.calls.append((city, country_iso2, admin1_code))
        return self.places.get((city.lower(), country_iso2, admin1_code))


def _first_call():
    """Import time and first-call latency, in a fresh interpreter."""
    code = (
        "import time; t = time.perf_counter(); from placewise.text import parse_location; "
        "t1 = time.perf_counter(); parse_location('Toronto, ON'); t2 = time.perf_counter(); "
        "parse_location('Hybrid - Mumbai, MH or Remote (EMEA)'); t3 = time.perf_counter(); "
        "print(t1 - t, t2 - t1, t3 - t2)"
    )
    best = None
    for _ in range(5):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        times = tuple(map(float, out.stdout.split()))
        best = times if best is None else tuple(map(min, best, times))
    return best


def main():
    args = sys.argv[1:]
    dump = None
    if "--dump" in args:
        i = args.index("--dump")
        dump = Path(args[i + 1])
        del args[i : i + 2]
    n = int(args[0]) if args else 20_000

    imp, first, second = _first_call()
    print(f"import placewise.text               {imp * 1000:8.1f} ms")
    print(f"first parse_location (tables)       {first * 1000:8.1f} ms")
    print(f"second parse_location               {second * 1000:8.1f} ms")

    tracemalloc.start()
    from placewise.text import LocationFilter, parse_location

    parse_location("Toronto, ON")
    parse_location("Hybrid - Mumbai, MH or Remote (EMEA)")
    size, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"memory after import + first calls   {size / 1e6:8.2f} MB")

    strings = corpus(n)
    unique = list(dict.fromkeys(strings))
    print(f"corpus: {len(strings):,} strings, {len(unique):,} unique")
    t = time.process_time()
    results = [parse_location(s) for s in unique]
    dt = time.process_time() - t
    print(f"parse_location, unique strings      {dt:8.3f} s  = {len(unique) / dt:,.0f} /s")
    t = time.process_time()
    for s in unique:
        parse_location(s)
    dt = time.process_time() - t
    print(f"parse_location, second pass         {dt:8.3f} s  = {len(unique) / dt:,.0f} /s")
    gazetteer = BenchGazetteer()
    t = time.process_time()
    with_gazetteer = [parse_location(s, gazetteer) for s in unique]
    dt = time.process_time() - t
    print(f"parse_location, with a gazetteer    {dt:8.3f} s  = {len(unique) / dt:,.0f} /s")
    t = time.process_time()
    with_context = [parse_location(s, context="CA") for s in unique]
    dt = time.process_time() - t
    print(f"parse_location, context='CA'        {dt:8.3f} s  = {len(unique) / dt:,.0f} /s")

    flt = LocationFilter(countries=("CA", "US"), admin1=("CA-ON",), metros=("Bay Area",))
    t = time.process_time()
    decisions = [flt.decide(p) for p in results]
    dt = time.process_time() - t
    print(f"LocationFilter.decide (parsed)      {dt:8.3f} s  = {len(unique) / dt:,.0f} /s")

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"peak RSS after the runs             {peak:8.1f} MB")

    lines = [repr(x) for x in (*results, *with_gazetteer, *with_context, *decisions, *gazetteer.calls)]
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    print(f"results digest {digest[:16]}")
    if dump is not None:
        dump.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
