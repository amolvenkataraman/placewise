"""Lookup benchmark on the real world pack (not collected by pytest):

    uv run python tests/lookup/bench_lookup.py [N]

N random land points (default 100,000), uniform on the sphere, kept when inside a country polygon.
"""

import sys
import time
from pathlib import Path

import numpy as np

from placewise.engine import Geocoder
from placewise.packs import open_pack

PACK = Path(__file__).resolve().parents[2] / ".cache" / "packbuild" / "out" / "world-2026.11"


def land_points(pack, n, seed=0):
    rng = np.random.default_rng(seed)
    countries = pack["countries"]
    lats, lons = [], []
    while sum(map(len, lats)) < n:
        lat = np.degrees(np.arcsin(rng.uniform(-1, 1, 4 * n)))
        lon = rng.uniform(-180, 180, 4 * n)
        land = countries.query(lat, lon) >= 0
        lats.append(lat[land])
        lons.append(lon[land])
    return np.concatenate(lats)[:n], np.concatenate(lons)[:n]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    pack = open_pack(PACK)
    lat, lon = land_points(pack, n)
    t = time.perf_counter()
    geo = Geocoder(packs=[pack])
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
    print(f"{with_city / n:.1%} of land points have a city within the radius")


if __name__ == "__main__":
    main()
