"""A synthetic world-postal pack over lookup_kit's invented Pacific world (nothing real), with the
real pack's columns (packbuild.sources.geonames_postal).

XA (Alphaland, lat 0..1, lon -140..-139): A100 at Alpha City and a second point to its east;
    A200 at Southby; reach 10 km
XB (Betaland, lon -139..-138): B-1 just over the border from Alphaland; reach 30 km
XC (Gammaland, an island): one code, GC1, which answers anywhere on it
"""

import numpy as np

from placewise.packs import LayerData, write_pack

CREATED = "2026-11-17T00:00:00Z"

# id, code, place, country, lat, lon, reach km, secondary
ROWS = [
    ("postal:XA:A100", "A100", "Alpha City", "XA", 0.75, -139.5, 10.0, False),
    ("postal:XA:A100:2", "A100", "East Alpha", "XA", 0.75, -139.3, 10.0, True),
    ("postal:XA:A200", "A200", "Southby", "XA", 0.2, -139.2, 10.0, False),
    ("postal:XB:B1", "B-1", "Beta Town", "XB", 0.5, -138.98, 30.0, False),
    ("postal:XC:GC1", "GC1", "Gamma Port", "XC", 2.25, -139.75, 30.0, False),
]


def postal_layer(rows=ROWS):
    columns = {
        "id": [r[0] for r in rows],
        "name": [r[1] for r in rows],
        "codes": [r[1] for r in rows],
        "place": [r[2] for r in rows],
        "admin1": ["" for _ in rows],
        "admin2": ["" for _ in rows],
        "country": [r[3] for r in rows],
        "reach_km": np.array([r[6] for r in rows], dtype=np.uint8),
        "secondary": np.array([r[7] for r in rows], dtype=bool),
    }
    types = {k: "str" for k in columns} | {"reach_km": "u1", "secondary": "bool"}
    return LayerData(
        "postal", "point", columns, ("geonames",), lat=np.array([r[4] for r in rows]),
        lon=np.array([r[5] for r in rows]), types=types,
    )  # fmt: skip


def write_postal(out_dir, rows=ROWS):
    """The synthetic postcode pack, named like the real one: world-postal-2026.11."""
    return write_pack(out_dir, "world-postal", "2026.11", [postal_layer(rows)], created=CREATED)
