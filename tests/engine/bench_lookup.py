"""Lookup benchmark on the real packs (not collected by pytest):

    uv run python tests/engine/bench_lookup.py [N] [world|all] [land|countries]

N random points (default 100,000), uniform on the sphere, kept when inside a country polygon
("land") or inside the US, Canada or India ("countries", where the country packs do their work).
"world" reads the world pack alone; "all" adds the US, Canada and India packs.
"""

import sys
import time
from pathlib import Path

import numpy as np

from placewise.engine import Geocoder
from placewise.packs import open_pack

OUT = Path(__file__).resolve().parents[2] / ".cache" / "packbuild" / "out"
COUNTRY_PACKS = ("us", "ca", "in")


def land_points(pack, n, seed=0, only=None):
    """n random points inside a country polygon (of the ISO codes `only`, if given)."""
    rng = np.random.default_rng(seed)
    countries = pack["countries"]
    keep_rows = None
    if only:
        keep_rows = np.flatnonzero(np.isin(countries.column("iso2"), list(only)))
    lats, lons = [], []
    while sum(map(len, lats)) < n:
        lat = np.degrees(np.arcsin(rng.uniform(-1, 1, 4 * n)))
        lon = rng.uniform(-180, 180, 4 * n)
        rows = countries.query(lat, lon)
        land = rows >= 0 if keep_rows is None else np.isin(rows, keep_rows)
        lats.append(lat[land])
        lons.append(lon[land])
    return np.concatenate(lats)[:n], np.concatenate(lons)[:n]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    which = sys.argv[2] if len(sys.argv) > 2 else "world"
    where = sys.argv[3] if len(sys.argv) > 3 else "land"
    pack = open_pack(OUT / "world-2026.11")
    packs = [pack] + ([open_pack(OUT / f"{p}-2026.11") for p in COUNTRY_PACKS] if which == "all" else [])
    lat, lon = land_points(pack, n, only=("US", "CA", "IN") if where == "countries" else None)
    print(f"packs: {', '.join(p.name for p in packs)}; points: {where}")
    t = time.perf_counter()
    geo = Geocoder(packs=packs)
    print(f"Geocoder()                       {time.perf_counter() - t:8.3f} s")
    t = time.perf_counter()
    geo.lookup(43.6426, -79.3871)
    print(f"first lookup (lazy indexes)      {time.perf_counter() - t:8.3f} s")
    t = time.perf_counter()
    geo.lookup_many(lat[:1000], lon[:1000])
    print(f"warm-up lookup_many(1k)          {time.perf_counter() - t:8.3f} s")
    for label in ("first pass", "second pass"):  # the first also fills the place caches
        t = time.perf_counter()
        results = geo.lookup_many(lat, lon)
        dt = time.perf_counter() - t
        print(f"lookup_many({n:,}) {label:<12} {dt:8.3f} s  = {n / dt:,.0f} points/s")
    t = time.perf_counter()
    geo.lookup_many(lat, lon, near=False)
    dt = time.perf_counter() - t
    print(f"lookup_many({n:,}) near=False   {dt:8.3f} s  = {n / dt:,.0f} points/s")
    t = time.perf_counter()
    for a, b in zip(lat[:2000], lon[:2000], strict=True):
        geo.lookup(float(a), float(b))
    dt = time.perf_counter() - t
    print(f"lookup() x 2,000                 {dt:8.3f} s  = {2000 / dt:,.0f} points/s")
    with_city = sum(r.city is not None for r in results)
    print(f"{with_city / n:.1%} of points have a city")


if __name__ == "__main__":
    main()
