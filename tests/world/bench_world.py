"""World-query benchmark (not collected by pytest):

    uv run python tests/world/bench_world.py [--dump FILE]

Times each placewise.world query over every country, group and subdivision (CPU time, best of 3),
the first call (indexes are built lazily) in a fresh interpreter, and prints a digest of every
answer; `--dump` writes the answers, one per line, for diffing.
"""

import hashlib
import subprocess
import sys
import time
from pathlib import Path


def _first_call():
    code = (
        "import time; t = time.perf_counter(); from placewise import world; t1 = time.perf_counter(); "
        "world.is_member('GB', 'EU', on='2019-06-01'); world.subregion('Ontario'); "
        "t2 = time.perf_counter(); print(t1 - t, t2 - t1)"
    )
    best = None
    for _ in range(5):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        times = tuple(map(float, out.stdout.split()))
        best = times if best is None else tuple(map(min, best, times))
    return best


def _timed(label, fn, n):
    best, out = None, None
    for _ in range(3):
        t = time.process_time()
        out = fn()
        dt = time.process_time() - t
        best = dt if best is None else min(best, dt)
    print(f"{label:34} {best * 1000:9.2f} ms  = {n / best:>12,.0f} /s")
    return out


def main():
    args = sys.argv[1:]
    dump = Path(args[args.index("--dump") + 1]) if "--dump" in args else None
    imp, first = _first_call()
    print(f"import placewise.world             {imp * 1000:9.2f} ms")
    print(f"first is_member + subregion        {first * 1000:9.2f} ms")

    from placewise import world
    from placewise.constants import countries as table

    codes = [c.alpha2 for c in table.COUNTRIES]
    names = [c.name for c in table.COUNTRIES] + [c.alpha3.lower() for c in table.COUNTRIES]
    group_ids = [g.id for g in world.groups()]
    subs = [(s.code, s.name) for a in table.SUBREGIONS for s in world.subregions(a)]
    dates = ("2019-06-01", "2000-01-01", "2026-01-01")
    lines = []

    def answers(xs):
        lines.extend(map(repr, xs))

    answers(_timed("country(code)", lambda: [world.country(c) for c in codes], len(codes)))
    answers(_timed("country(name / alpha-3)", lambda: [world.country(c) for c in names], len(names)))
    pairs = [(c, g, d) for c in codes[::4] for g in group_ids[::3] for d in dates]
    answers(_timed("is_member", lambda: [world.is_member(c, g, d) for c, g, d in pairs], len(pairs)))
    answers(_timed("groups(of=)", lambda: [world.groups(of=c) for c in codes[::5]], len(codes[::5])))
    answers(
        _timed("countries(group=)", lambda: [world.countries(group=g) for g in group_ids], len(group_ids))
    )
    answers(
        _timed("members()", lambda: [world.members(g, as_of="2019-06-01") for g in group_ids], len(group_ids))
    )
    answers(_timed("subregion(code)", lambda: [world.subregion(c) for c, _ in subs], len(subs)))
    answers(_timed("subregion(name)", lambda: [world.subregion(n) for _, n in subs], len(subs)))
    answers(
        _timed(
            "subregion(x, country=)",
            lambda: [world.subregion(c.split("-", 1)[1], country=c[:2]) for c, _ in subs],
            len(subs),
        )
    )
    answers(_timed("regions(country)", lambda: [world.regions(c) for c in ("US", "CA", "IN", "GB")], 4))
    digest = hashlib.sha256("\n".join(lines).encode()).hexdigest()
    print(f"answers digest {digest[:16]}")
    if dump is not None:
        dump.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
