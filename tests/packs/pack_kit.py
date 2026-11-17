"""Synthetic shapes and helpers for the pack tests: no real data, nothing personal."""

import math

import numpy as np

from placewise.model import Feature, Outline
from placewise.packs import LayerData

CREATED = "2026-11-17T00:00:00Z"


def e7(x):
    """Round to the 1e-7 degree grid packs store, so brute-force answers see the same geometry."""
    return round(float(x), 7)


def rect(south, west, north, east):
    """A counter-clockwise box ring."""
    return tuple((e7(a), e7(b)) for a, b in ((south, west), (south, east), (north, east), (north, west)))


def box_feature(south, west, north, east, *holes, fid=None):
    rings = (rect(south, west, north, east), *(rect(*h)[::-1] for h in holes))
    return Feature(outlines=(Outline(rings),), id=fid)


def blob_ring(lat, lon, radius_deg, n, rng, wiggle=0.25):
    """A star-shaped ring of n vertices around (lat, lon): a crude country or lake outline."""
    theta = np.sort(rng.uniform(0, 2 * math.pi, n))
    r = radius_deg * (1 + wiggle * np.sin(5 * theta) + wiggle * rng.uniform(-0.5, 0.5, n))
    lats = np.clip(lat + r * np.sin(theta), -89.9, 89.9)
    lons = np.clip(lon + r * np.cos(theta) / max(math.cos(math.radians(lat)), 0.2), -179.9, 179.9)
    return tuple((e7(a), e7(b)) for a, b in zip(lats, lons, strict=True))


def blob_features(count, rng, radius=(1.0, 6.0), vertices=(8, 200), lat_range=(-70, 70), holes=False):
    features = []
    for _ in range(count):
        lat, lon = rng.uniform(*lat_range), rng.uniform(-170, 170)
        radius_deg = rng.uniform(*radius)
        rings = [blob_ring(lat, lon, radius_deg, int(rng.integers(*vertices)), rng)]
        if holes:
            # a lake well inside the core (the outer ring never comes nearer than ~0.5 radius)
            rings.append(blob_ring(lat, lon, radius_deg * 0.25, 12, rng, wiggle=0.1)[::-1])
        outlines = [Outline(tuple(rings))]
        if holes and rng.uniform() < 0.5:  # an offshore island makes it a multipolygon
            island_lat = min(max(lat + radius_deg * 2.2, -89), 89)
            outlines.append(Outline((blob_ring(island_lat, lon, radius_deg * 0.3, 10, rng, 0.1),)))
        features.append(Feature(outlines=tuple(outlines)))
    return features


def fiji():
    """Spans 170°E to 170°W, split at the antimeridian as RFC 7946 asks."""
    east = Outline((rect(-19, 170, -16, 180),))
    west = Outline((rect(-19, -180, -16, -170),))
    return Feature(outlines=(east, west), id="synthetic:fiji")


def brute_force(features, lats, lons):
    """First feature containing each point, or -1, by testing every feature."""
    out = np.full(np.shape(lats), -1, dtype=np.int64)
    for i in reversed(range(len(features))):  # reversed so the first match wins
        out[np.asarray(features[i].contains(lats, lons))] = i
    return out


def polygon_layer(features, name="areas", cell_deg=1.0, **columns):
    n = len(features)
    cols = {"id": [f"synthetic:{name}:{i}" for i in range(n)], "name": [f"Area {i}" for i in range(n)]}
    cols.update(columns)
    return LayerData(
        name=name, kind="polygon", columns=cols, sources=("synthetic",), features=features, cell_deg=cell_deg
    )


def point_layer(lat, lon, name="spots", **columns):
    n = len(lat)
    cols = {"id": [f"synthetic:{name}:{i}" for i in range(n)], "name": [f"Spot {i}" for i in range(n)]}
    cols.update(columns)
    return LayerData(
        name=name,
        kind="point",
        columns=cols,
        sources=("synthetic",),
        lat=np.asarray(lat, dtype=np.float64),
        lon=np.asarray(lon, dtype=np.float64),
    )
