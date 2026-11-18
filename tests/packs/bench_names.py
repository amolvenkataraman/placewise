"""Name index benchmark (not collected by pytest), on a built pack:

    uv run python tests/packs/bench_names.py ~/.placewise/packbuild/out/world-2026.11 [layer]

Queries are names from the pack's own layer (default: its first indexed layer with the most
rows): exact names, their first four characters as prefixes, and the names with one character
dropped as typos. Prints the cold costs (opening, first fuzzy lookup reading the trigram
postings, or building them for older packs) and the warm mean and 95th percentile per query.
"""

import sys
import time

import numpy as np

from placewise.packs import open_pack


def per_query(label, fn, queries):
    times = []
    hits = 0
    for q in queries:
        t = time.perf_counter()
        hits += len(fn(q)) > 0
        times.append(time.perf_counter() - t)
    ms = np.array(times) * 1000
    p95 = np.percentile(ms, 95)
    print(f"{label:<28} mean {ms.mean():7.3f} ms   p95 {p95:7.3f} ms   hits {hits}/{len(queries)}")


def main(path, layer=None, count=2000, seed=0):
    t = time.perf_counter()
    pack = open_pack(path)
    idx = pack.names
    print(f"{pack!r}: open {1000 * (time.perf_counter() - t):.1f} ms, {len(idx)} entries")
    layer = layer or max(idx.layers, key=lambda name: len(pack[name]))
    rng = np.random.default_rng(seed)
    names = pack[layer].column("name")
    picked = [n for n in names[rng.choice(len(names), size=min(count, len(names)), replace=False)] if n]
    typos = []
    for n in picked:
        i = int(rng.integers(len(n)))
        typos.append(n[:i] + n[i + 1 :] if len(n) > 4 else n)
    t = time.perf_counter()
    idx.exact(picked[0])
    print(f"first exact (loads key table)  {1000 * (time.perf_counter() - t):7.1f} ms")
    t = time.perf_counter()
    idx.fuzzy(typos[0])
    print(f"first fuzzy (reads trigrams)   {1000 * (time.perf_counter() - t):7.1f} ms")
    print(f"{len(picked)} names from {layer!r}")
    per_query("exact", idx.exact, picked)
    per_query("prefix (4 chars, limit 10)", lambda q: idx.prefix(q[:4]), picked)
    per_query("fuzzy (1 char dropped)", idx.fuzzy, typos)
    ids = pack[layer].column("id")
    per_query("codes (row ids)", idx.codes, [ids[i] for i in rng.choice(len(ids), size=500)])


if __name__ == "__main__":
    main(sys.argv[1], *(sys.argv[2:3] or []))
