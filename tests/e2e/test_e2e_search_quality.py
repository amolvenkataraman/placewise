"""Search ranking evaluation on the real packs: does `find` return what a person means?

The cases (search_quality_cases.json beside this file, public places only) give each query the
placewise id expected first; an Entity matches when its id or one of its alternates' ids is listed.
Each case is a test of its own (`known` ones are expected failures the data can't fix yet), and
`test_search_quality_report` prints top-1 and top-3 accuracy per category and warm latency, and
holds the accuracy above a floor so ranking changes can't quietly make search worse.

Run: E2E_PACKS_DIR=... uv run pytest tests/e2e/test_e2e_search_quality.py -s"""

import json
import time
from pathlib import Path

import pytest
from e2e_kit import geocoder

PACKS = (
    "world",
    "usa",
    "can",
    "ind",
    "world-water",
    "usa-parks",
    "can-parks",
    "world-parks",
    "world-notable",
)
CASES = json.loads((Path(__file__).with_name("search_quality_cases.json")).read_text(encoding="utf-8"))[
    "cases"
]
# accuracy over the cases the packs can run (known failures included): 98.3% top-1 and 99.4%
# top-3 on the 2026.11 packs; the floors leave room for a case or two
TOP1_FLOOR = 0.97
TOP3_FLOOR = 0.99
LATENCY_REPEATS = 3


@pytest.fixture(scope="module")
def geo():
    found = geocoder(*PACKS)
    if any(p.names is None for p in found.packs):
        pytest.skip("packs without a name index (rebuild them with names/)")
    return found


def options(case):
    found = dict(case.get("options", {}))
    if "near" in found:
        found["near"] = tuple(found["near"])
    return found


def missing_needs(geo, case):
    """The case's `needs` the open packs lack: "pack:layer.column" (the layer has the column) or
    "pack:layer:Name>rank" (the pack's name index ranks Name in that layer above rank)."""
    packs = {p.name: p for p in geo.packs}
    return [need for need in case.get("needs", ()) if not _has(packs, need)]


def _has(packs, need):
    pack, _, rest = need.partition(":")
    p = packs.get(pack)
    if ">" in rest:
        layer, _, name = rest.partition(":")
        name, _, least = name.partition(">")
        found = p.names.exact(name) if p is not None else None
        if found is None or layer not in p.names.layers:
            return False
        return bool((found.rank[found.layer == p.names.layers.index(layer)] > float(least)).any())
    layer, _, column = rest.partition(".")
    return p is not None and layer in p and column in p[layer].fields


def ids(entity):
    return {entity.place.id, *(a.id for a in entity.alternates)}


def ranks(geo, case):
    """(position of the first expected id or None, every top3 id within the first three, the
    first three Entities)."""
    found = geo.find(case["q"], limit=10, **options(case))
    first = next((i for i, e in enumerate(found) if ids(e) & set(case["top"])), None)
    top3 = set().union(*(ids(e) for e in found[:3])) if found else set()
    return first, all(i in top3 for i in case.get("top3", ())), found[:3]


def describe(found):
    return [f"{e.place.id} {e.place.name} ({e.region}, {e.country})" for e in found]


def _param(case):
    label = case["q"] + (f" {case['options']}" if case.get("options") else "")
    marks = [pytest.mark.xfail(reason=case["known"], strict=False)] if case.get("known") else []
    return pytest.param(case, id=label, marks=marks)


@pytest.mark.parametrize("case", [_param(c) for c in CASES])
def test_search_quality(geo, case):
    if missing := missing_needs(geo, case):
        pytest.skip(f"packs without {', '.join(missing)}")
    first, top3, found = ranks(geo, case)
    assert first == 0 and top3, (case["q"], case["top"], case.get("top3"), describe(found))


def test_search_quality_report(geo, capsys):
    runnable = [c for c in CASES if not missing_needs(geo, c)]
    per = {}
    misses = []
    for case in runnable:
        first, top3, found = ranks(geo, case)
        hit1 = first == 0 and top3
        hit3 = first is not None and first < 3 and top3
        stats = per.setdefault(case["category"], [0, 0, 0])
        stats[0] += 1
        stats[1] += hit1
        stats[2] += hit3
        if not hit1:
            misses.append((case, describe(found)))
    warm = []
    for case in runnable:
        geo.find(case["q"], limit=10, **options(case))
        t = time.perf_counter()
        for _ in range(LATENCY_REPEATS):
            geo.find(case["q"], limit=10, **options(case))
        warm.append((time.perf_counter() - t) * 1000 / LATENCY_REPEATS)
    warm.sort()
    n = len(runnable)
    top1 = sum(s[1] for s in per.values()) / n
    top3 = sum(s[2] for s in per.values()) / n
    with capsys.disabled():
        print(f"\nsearch quality: {n} cases ({len(CASES) - n} skipped): top-1 {top1:.1%}, top-3 {top3:.1%}")
        for category, (count, one, three) in sorted(per.items()):
            print(f"  {category:14s} {count:3d}  top-1 {one / count:6.1%}  top-3 {three / count:6.1%}")
        p50, p95 = warm[n // 2], warm[int(n * 0.95)]
        print(f"warm latency: median {p50:.1f} ms, p95 {p95:.1f} ms, max {warm[-1]:.1f} ms")
        for case, found in misses:
            tag = " (known)" if case.get("known") else ""
            print(f"  miss{tag}: {case['q']!r} {case.get('options', '')} -> {found}")
    assert top1 >= TOP1_FLOOR and top3 >= TOP3_FLOOR, (top1, top3)
