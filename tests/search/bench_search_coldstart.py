"""Forward search cold-start benchmark (not collected by pytest), on built packs:

    uv run python tests/search/bench_search_coldstart.py [packs dir] [--runs 3] [--digest out.json]

Every query runs in a fresh process: open the packs (world, usa, can, ind, world-water and the
park packs), time the first find(), then the same query warm (median of 20). Each query's
first-call time is the best of --runs processes, so a busy machine weighs less. --digest writes
every query's results (ids, names, scores), so two checkouts can be compared for identical
answers:

    PYTHONPATH=<other checkout>/src uv run python tests/search/bench_search_coldstart.py --digest a.json

The packs dir defaults to where packbuild writes them (~/.placewise/packbuild/out); the newest
`<name>-<version>` directory of each pack wins. Run it through the heavy-job wrapper on a shared
machine: it opens the real packs.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

PACKS = ("world", "usa", "can", "ind", "world-water", "usa-parks", "can-parks", "world-parks")
QUERIES = (
    ("YYZ", {}),  # an airport code: the served city, then the airport with its city context
    ("Torono", {}),  # a typo: fuzzy matching
    ("Paris", {"country": "USA"}),
    ("M5V", {}),  # a postal code with its city context
    ("Toronto", {}),
    ("Yosemite", {}),
    ("94105", {}),
    ("Bengaluru", {}),
    ("Mississ", {"prefix": True}),
    ("43.6426, -79.3871", {}),  # coordinates: a full reverse lookup
)
WARM_RUNS = 20

_CHILD = """
import json, statistics, sys, time
from placewise.engine import Geocoder
from placewise.packs import open_pack
paths, text, options, warm_runs = json.loads(sys.argv[1])
t = time.perf_counter()
geo = Geocoder(packs=[open_pack(p) for p in paths])
opened = time.perf_counter() - t
t = time.perf_counter()
found = geo.find(text, **options)
first = time.perf_counter() - t
warm = []
for _ in range(warm_runs):
    t = time.perf_counter()
    again = geo.find(text, **options)
    warm.append(time.perf_counter() - t)
assert [e.to_dict() for e in again] == [e.to_dict() for e in found]
results = [[e.place.id, e.place.name, e.place.kind.value, e.city, e.region, e.country, e.score]
           for e in found]
print(json.dumps({"open": opened, "first": first, "warm": statistics.median(warm), "results": results}))
"""


def pack_paths(root):
    from placewise.store.paths import parse_pack_dir

    paths = []
    for name in PACKS:
        found = sorted(
            p
            for p in root.glob(f"{name}-*")
            if (p / "pack.json").is_file() and (parse_pack_dir(p.name) or ("",))[0] == name
        )
        if not found:
            sys.exit(f"pack {name!r} is not built in {root}")
        paths.append(str(found[-1]))
    return paths


def run(paths, text, options):
    out = subprocess.run(
        [sys.executable, "-c", _CHILD, json.dumps([paths, text, options, WARM_RUNS])],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # the checkout, for packbuild
    from packbuild.fetch import DEFAULT_CACHE

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("packs", nargs="?", type=Path, default=DEFAULT_CACHE / "out")
    parser.add_argument("--runs", type=int, default=3, help="fresh processes per query (best first call)")
    parser.add_argument("--digest", type=Path, help="write every query's results here (JSON)")
    args = parser.parse_args(argv)
    paths = pack_paths(args.packs)
    print(f"{'query':<34} {'first ms':>9} {'warm ms':>8}  top result")
    digest = {}
    for text, options in QUERIES:
        runs = [run(paths, text, options) for _ in range(args.runs)]
        best = min(runs, key=lambda r: r["first"])
        warm = min(r["warm"] for r in runs)
        label = text + "".join(f" {k}={v}" for k, v in options.items())
        top = best["results"][0][1] if best["results"] else "-"
        print(f"{label:<34} {1000 * best['first']:9.1f} {1000 * warm:8.2f}  {top}")
        digest[label] = best["results"]
        if any(r["results"] != best["results"] for r in runs):
            print(f"  ! {label}: results differ between processes")
    if args.digest:
        args.digest.write_text(json.dumps(digest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
