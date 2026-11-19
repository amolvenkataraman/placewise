"""Synthetic park packs over lookup_kit's invented world (open Pacific water, nothing real).

Alphaland (lat 0 - 1, lon -140 .. -139):

    North Forest          tier 2   0.55 - 0.95, -139.95 .. -139.55
      Alpha National Park tier 1   0.60 - 0.90, -139.90 .. -139.60
        Alpha Preserve    tier 1   0.70 - 0.80, -139.80 .. -139.70   (smaller: listed first)
    Marsh Conservation    tier 3   0.20 - 0.25, -139.10 .. -139.05
    Town Green            tier 4   two parcels of one park: 0.10 - 0.11 and 0.12 - 0.13, -139.30 .. -139.29
    "Open Space"          tier 3   0.30 - 0.31, -139.20 .. -139.19   (a generic name, as old packs have)

Gammaland (lat 2 - 2.5, lon -140 .. -139.5): Gamma National Park, a point at (2.25, -139.6) with a
5 km radius (world-parks/park_points), and Gamma Sanctuary, a point without an area (radius 0).
Alpha National Park is a point too (5 km round its middle), as world-parks has Europe's parks that
eur-parks draws.
"""

import numpy as np
from lookup_kit import CREATED, box_feature

from placewise.packs import LayerData, write_pack

# layer, row id, park id, name, tier, designation, area_km2, box
POLYGONS = [
    ("parks_national", "nps:ALPH", "nps:ALPH", "Alpha National Park", 1, "National Park", 1100.0,
     (0.6, -139.9, 0.9, -139.6)),
    ("parks_national", "nps:ALPR", "nps:ALPR", "Alpha Preserve", 1, "National Preserve", 120.0,
     (0.7, -139.8, 0.8, -139.7)),
    ("parks_state", "usfs:0101", "usfs:0101", "North Forest", 2, "National Forest", 2000.0,
     (0.55, -139.95, 0.95, -139.55)),
    ("parks_regional", "pad-us:xa:sca:marsh#1", "pad-us:xa:sca:marsh", "Marsh Conservation Area", 3,
     "State Conservation Area", 30.0, (0.2, -139.1, 0.25, -139.05)),
    ("parks_local", "pad-us:xa:lp:town-green#1", "pad-us:xa:lp:town-green", "Town Green", 4, "Local Park",
     2.4, (0.10, -139.30, 0.11, -139.29)),
    ("parks_local", "pad-us:xa:lp:town-green#2", "pad-us:xa:lp:town-green", "Town Green", 4, "Local Park",
     2.4, (0.12, -139.30, 0.13, -139.29)),
    ("parks_regional", "pad-us:xa:lca:open-space", "pad-us:xa:lca:open-space", "Open Space", 3,
     "Local Conservation Area", 1.2, (0.30, -139.20, 0.31, -139.19)),
]  # fmt: skip

# id, name, tier, designation, area_km2, radius_km, lat, lon
POINTS = [
    ("wikidata:Q1", "Gamma National Park", 1, "national park", 78.5, 5.0, 2.25, -139.6),
    ("wikidata:Q2", "Gamma Sanctuary", 2, "wildlife sanctuary", float("nan"), 0.0, 2.4, -139.9),
    ("wikidata:Q3", "Unknown Park", 2, "wildlife sanctuary", float("nan"), 0.0, 2.1, -139.9),
    ("wikidata:Q4", "ALPHA National  Park", 1, "national park", 78.5, 5.0, 0.75, -139.75),
    ("wikidata:Q5", "Alpha NP", 1, "national park", 10.0, 1.0, 0.65, -139.65),  # the park's alias
]


def polygon_layers():
    out = []
    for name in dict.fromkeys(p[0] for p in POLYGONS):
        rows = [p for p in POLYGONS if p[0] == name]
        columns = {
            "id": [r[1] for r in rows],
            "park": [r[2] for r in rows],
            "name": [r[3] for r in rows],
            "tier": np.array([r[4] for r in rows], dtype=np.uint8),
            "designation": [r[5] for r in rows],
            "area_km2": np.array([r[6] for r in rows], dtype=np.float32),
            "aliases": ["Alpha NP" if r[3] == "Alpha National Park" else "" for r in rows],
        }
        features = [box_feature(*r[7], fid=r[1]) for r in rows]
        out.append(LayerData(name, "polygon", columns, ("synthetic",), features=features))
    return out


def points_layer():
    columns = {
        "id": [p[0] for p in POINTS],
        "name": [p[1] for p in POINTS],
        "tier": np.array([p[2] for p in POINTS], dtype=np.uint8),
        "designation": [p[3] for p in POINTS],
        "area_km2": np.array([p[4] for p in POINTS], dtype=np.float32),
        "radius_km": np.array([p[5] for p in POINTS], dtype=np.float32),
    }
    lat, lon = np.array([p[6] for p in POINTS]), np.array([p[7] for p in POINTS])
    return LayerData("park_points", "point", columns, ("synthetic",), lat=lat, lon=lon)


def write_parks(out_dir):
    """(usa-parks-2026.11, world-parks-2026.11), named like the real packs."""
    outlines = write_pack(out_dir, "usa-parks", "2026.11", polygon_layers(), created=CREATED)
    points = write_pack(out_dir, "world-parks", "2026.11", [points_layer()], created=CREATED)
    return outlines, points
