"""Pack benchmark on synthetic data (not collected by pytest): uv run python tests/packs/bench_packs.py

250 country-sized polygons with ~1M vertices in all; 1M point queries; nearest over 200k points.
"""

import math
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from pack_kit import blob_ring, point_layer, polygon_layer

from placewise.model import Feature, Outline
from placewise.packs import open_pack, write_pack


def countries(rng, count=250, vertices=4000):
    # centres on a jittered lattice so neighbours rarely overlap, like real countries
    lats = np.linspace(-55, 65, 15)
    lons = np.linspace(-170, 170, 17)
    centres = [(a, b) for a in lats for b in lons][:count]
    features = []
    for lat, lon in centres:
        radius = rng.uniform(2.5, 4.0)
        ring = blob_ring(lat + rng.uniform(-1, 1), lon + rng.uniform(-1, 1), radius, vertices, rng, 0.2)
        features.append(Feature(outlines=(Outline((ring,)),)))
    return features


def timed(label, fn, repeat=1):
    best = math.inf
    for _ in range(repeat):
        t = time.perf_counter()
        result = fn()
        best = min(best, time.perf_counter() - t)
    print(f"{label:<52} {best * 1000:9.1f} ms")
    return result


def main():
    rng = np.random.default_rng(2026)
    with tempfile.TemporaryDirectory() as tmp:
        features = countries(rng)
        n_vertices = sum(len(r) for f in features for o in f.outlines for r in o.rings)
        print(f"{len(features)} polygons, {n_vertices:,} vertices")

        n_points = 200_000
        u = n_points // 2
        plat = np.concatenate([np.degrees(np.arcsin(rng.uniform(-1, 1, u))), rng.normal(48, 3, u // 2),
                               rng.normal(22, 4, u - u // 2)])  # fmt: skip
        plon = np.concatenate(
            [rng.uniform(-180, 180, u), rng.normal(10, 6, u // 2), rng.normal(80, 5, u - u // 2)]
        )
        plat, plon = np.clip(plat, -90, 90), (plon + 180) % 360 - 180

        layers = [polygon_layer(features, name="countries"), point_layer(plat, plon, name="cities")]
        path = timed("write pack", lambda: write_pack(tmp, "bench", "2026.11", layers))
        size = sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())
        print(f"{'pack size on disk':<52} {size / 1e6:9.1f} MB")

        timed("open_pack (manifests only)", lambda: open_pack(path), repeat=5)
        timed("open_pack(verify=True)", lambda: open_pack(path, verify=True))
        pack = open_pack(path)
        countries_layer, cities = pack["countries"], pack["cities"]

        n = 1_000_000
        world_lat, world_lon = np.degrees(np.arcsin(rng.uniform(-1, 1, n))), rng.uniform(-180, 180, n)
        timed(
            "first 1M query, uniform (maps arrays, builds fine grids)",
            lambda: countries_layer.query(world_lat, world_lon),
        )
        hits = timed(
            "query 1M points, uniform over the world", lambda: countries_layer.query(world_lat, world_lon), 3
        )
        print(f"{'':<52} {np.mean(hits >= 0):9.1%} matched")
        boxes = np.array([f.bbox.as_tuple() for f in features])
        pick = rng.integers(0, len(boxes), n)
        s, w, nn, e = boxes[pick].T
        land_lat, land_lon = rng.uniform(s, nn), rng.uniform(w, e)
        timed("first 1M query inside polygon bboxes", lambda: countries_layer.query(land_lat, land_lon))
        hits = timed(
            "query 1M points, all inside polygon bboxes", lambda: countries_layer.query(land_lat, land_lon), 3
        )
        print(f"{'':<52} {np.mean(hits >= 0):9.1%} matched")
        rows, cols = countries_layer.grid_shape
        inside = np.asarray(countries_layer.grid_inside)
        cell = np.clip(np.floor(land_lat + 90), 0, rows - 1) * cols + np.clip(
            np.floor(land_lon + 180), 0, cols - 1
        )
        print(f"{'':<52} {np.mean(inside[cell.astype(int)] >= 0):9.1%} answered by inside cells")

        timed("nearest: build point grid (200k points)", lambda: cities.index)
        print(f"{'':<52} {cities.index.cell_deg:9g} deg cells")
        q = 100_000
        qlat, qlon = (
            plat[rng.integers(0, n_points, q)] + rng.normal(0, 0.2, q),
            plon[rng.integers(0, n_points, q)],
        )
        qlat = np.clip(qlat, -90, 90)
        timed("nearest k=1, 100k queries near the points", lambda: cities.nearest(qlat, qlon), 3)
        timed("nearest k=5, 100k queries near the points", lambda: cities.nearest(qlat, qlon, k=5), 3)
        ulat, ulon = np.degrees(np.arcsin(rng.uniform(-1, 1, q))), rng.uniform(-180, 180, q)
        timed("nearest k=1, 100k queries uniform over the world", lambda: cities.nearest(ulat, ulon), 3)
        timed("nearest k=1 max_km=25, 100k uniform queries", lambda: cities.nearest(ulat, ulon, max_km=25), 3)
        timed(
            "within 50 km, 1000 single queries",
            lambda: [cities.within(a, b, 50) for a, b in zip(qlat[:1000], qlon[:1000], strict=True)],
        )
        fresh = open_pack(path)["countries"]
        timed("cold: open + query 1M bbox points on a fresh pack", lambda: fresh.query(land_lat, land_lon))
        timed(
            "nearest_edge_km, 1000 points, one 4000-vertex polygon",
            lambda: countries_layer.nearest_edge_km(land_lat[:1000], land_lon[:1000], 0),
        )


if __name__ == "__main__":
    main()
