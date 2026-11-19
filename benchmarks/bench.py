"""Benchmark placewise on built packs: cold start, single lookups, batches and search.

    python benchmarks/bench.py --packs ~/.placewise/packs            # every pack found there
    python benchmarks/bench.py --packs DIR --version 2026.11.1 --json out.json

Numbers are wall-clock on one thread. Cold start runs in fresh processes, but the operating system
may still hold the pack files in its page cache (a truly cold disk is slower the first time).
Point sets are seeded, so runs are comparable:

- sphere: uniform on the globe (about 70% ocean)
- populated: world cities (GeoNames, 172k) jittered by ~3 km, every city equally likely
- usa-can-ind: the same, only cities in the US, Canada and India (full country-pack depth)
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

SEED = 2026
BATCH = 100_000
SINGLES = 2_000
SEARCH_REPEATS = 3
CASES = Path(__file__).resolve().parents[1] / "tests" / "e2e" / "search_quality_cases.json"

COLD = """
import time, json, sys
t0 = time.perf_counter()
import placewise
t1 = time.perf_counter()
geo = placewise.Geocoder(packs=json.loads(sys.argv[1]))
t2 = time.perf_counter()
geo.lookup(43.6532, -79.3832)
t3 = time.perf_counter()
geo.find("Toronto")
t4 = time.perf_counter()
print(json.dumps({"import_s": t1 - t0, "open_s": t2 - t1,
                  "first_lookup_s": t3 - t2, "first_find_s": t4 - t3}))
"""


def pack_dirs(root, version, only=None):
    dirs = sorted(
        p
        for p in Path(root).expanduser().glob(f"*-{version}" if version else "*-*")
        if (p / "pack.json").is_file()
    )
    if only:
        dirs = [p for p in dirs if p.name.rsplit("-", 1)[0] in only]
    # the world pack first: each world layer is read from the first pack that has it
    return sorted(dirs, key=lambda p: (not p.name.startswith("world-2"), p.name))


def cold(dirs):
    out = subprocess.run(
        [sys.executable, "-c", COLD, json.dumps([str(d) for d in dirs])],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def point_sets(world):
    rng = np.random.default_rng(SEED)
    z = rng.uniform(-1, 1, BATCH)
    sphere = (np.degrees(np.arcsin(z)), rng.uniform(-180, 180, BATCH))
    cities = world["cities"]
    lat, lon = np.asarray(cities.lat), np.asarray(cities.lon)
    country = np.asarray(cities.column("country")).astype(str)

    def jittered(mask):
        rows = rng.choice(np.flatnonzero(mask), BATCH)
        return lat[rows] + rng.normal(0, 0.03, BATCH), lon[rows] + rng.normal(0, 0.03, BATCH)

    return {
        "sphere": sphere,
        "populated": jittered(np.ones(len(lat), bool)),
        "usa-can-ind": jittered(np.isin(country, ["US", "CA", "IN"])),
    }


def pct(values, q):
    return float(np.percentile(np.asarray(values) * 1000, q))


def batches(geo, sets):
    out = {}
    for name, (lats, lons) in sets.items():
        for near in (True, False):
            t = time.perf_counter()
            geo.lookup_many(lats, lons, near=near)
            dt = time.perf_counter() - t
            out[f"{name}{'' if near else ' (near=False)'}"] = {
                "points": len(lats),
                "seconds": dt,
                "points_per_s": len(lats) / dt,
            }
    return out


def singles(geo, sets):
    out = {}
    for name in ("populated", "usa-can-ind"):
        lats, lons = sets[name]
        times = []
        for la, lo in zip(lats[:SINGLES].tolist(), lons[:SINGLES].tolist(), strict=True):
            t = time.perf_counter()
            geo.lookup(la, lo)
            times.append(time.perf_counter() - t)
        out[name] = {
            "n": len(times),
            "median_ms": pct(times, 50),
            "p95_ms": pct(times, 95),
            "p99_ms": pct(times, 99),
        }
    return out


def search(geo):
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    queries = [c["q"] for c in cases]
    prefixes = [q[: max(3, len(q) // 2)] for q in queries]
    for q in queries[:20]:
        geo.find(q)
    out = {}
    for label, fn, texts in (
        ("find", geo.find, queries),
        ("suggest", lambda t: geo.find(t, prefix=True), prefixes),
    ):
        times = []
        for _ in range(SEARCH_REPEATS):
            for text in texts:
                t = time.perf_counter()
                fn(text)
                times.append(time.perf_counter() - t)
        out[label] = {
            "queries": len(texts),
            "median_ms": pct(times, 50),
            "p95_ms": pct(times, 95),
            "p99_ms": pct(times, 99),
        }
    return out


def memory():
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("VmRSS", "RssAnon", "RssFile", "VmHWM"):
            fields[key] = int(value.split()[0]) / 1024  # MB
    return fields


def run(args):
    import placewise
    from placewise.packs import open_pack

    everything = pack_dirs(args.packs, args.version)
    world_only = [d for d in everything if d.name.startswith("world-2")]
    report = {
        "placewise": placewise.__version__,
        "python": platform.python_version(),
        "machine": platform.processor() or platform.machine(),
        "packs": [d.name for d in everything],
        "cold_world_only": cold(world_only),
        "cold_all_packs": cold(everything),
    }
    sets = point_sets(open_pack(world_only[0]))
    for label, dirs in (("world_only", world_only), ("all_packs", everything)):
        geo = placewise.Geocoder(packs=dirs)
        t = time.perf_counter()
        geo.lookup_many(*[a[:5000] for a in sets["populated"]])  # build the lazy indexes
        warm = time.perf_counter() - t
        report[label] = {"warmup_s": warm, "batch": batches(geo, sets), "single": singles(geo, sets)}
        if label == "all_packs":
            report[label]["search"] = search(geo)
            report[label]["memory_mb"] = memory()
        del geo
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--packs", required=True, help="directory holding <name>-<version> pack directories")
    parser.add_argument("--version", help="only packs of this version")
    parser.add_argument("--json", help="also write the report here")
    args = parser.parse_args(argv)
    report = run(args)
    text = json.dumps(report, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
