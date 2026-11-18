"""A synthetic world-notable pack over lookup_kit's invented world (open Pacific water).

Around (0.30, -139.60) in Alphaland's South Province, KM degrees of latitude = 1 km:

    Alpha Tower         landmark   fame 0.995  at the centre        (reaches 2 km)
    Alpha Museum        museum     fame 0.95   800 m north          (reaches 1 km)
    Corner Chapel       religious  fame 0.40   200 m east           (reaches 300 m)
    Little Bridge       bridge     fame 0.50   600 m south          (reaches 300 m: not the centre)
    Alpha Field Airport airport    fame 1.0    500 m west           (airports are never in `near`)
    Far Stadium         stadium    fame 0.999  11 km east           (2 km: too far)

and Midway Gate (landmark, fame 0.5) 100 m east of NEAR_CITY, a point whose Result.near names
the city Southam.
"""

import numpy as np
from lookup_kit import CREATED

from placewise.packs import LayerData, write_pack

CENTRE = (0.30, -139.60)
NEAR_CITY = (0.50, -139.80)
KM = 1 / 111.195  # degrees of latitude per km

# qid, name, kind, fame, lat, lon, aliases, iata
PLACES = [
    ("Q11", "Alpha Tower", "landmark", 0.995, 0.30, -139.60, "The Tower", ""),
    ("Q12", "Alpha Museum", "museum", 0.95, 0.30 + 0.8 * KM, -139.60, "", ""),
    ("Q13", "Corner Chapel", "religious_site", 0.40, 0.30, -139.60 + 0.2 * KM, "", ""),
    ("Q14", "Little Bridge", "bridge", 0.50, 0.30 - 0.6 * KM, -139.60, "", ""),
    ("Q15", "Alpha Field Airport", "airport", 1.0, 0.30, -139.60 - 0.5 * KM, "", "AFA"),
    ("Q16", "Far Stadium", "stadium", 0.999, 0.30, -139.50, "", ""),
    ("Q17", "Midway Gate", "landmark", 0.5, 0.50, -139.80 + 0.1 * KM, "", ""),
]


def notable_layer(places=PLACES):
    columns = {
        "id": [f"wikidata:{p[0]}" for p in places],
        "name": [p[1] for p in places],
        "aliases": [p[6] for p in places],
        "kind": [p[2] for p in places],
        "fame": np.array([p[3] for p in places], dtype=np.float32),
        "country": ["XA"] * len(places),
        "sitelinks": np.full(len(places), 10, dtype=np.uint16),
        "iata": [p[7] for p in places],
        "icao": [""] * len(places),
        "ipeds": [""] * len(places),
        "aishe": [""] * len(places),
        "station_code": [""] * len(places),
    }
    lat, lon = np.array([p[4] for p in places]), np.array([p[5] for p in places])
    return LayerData("notable", "point", columns, ("synthetic",), lat=lat, lon=lon)


def write_notable(out_dir, places=PLACES):
    return write_pack(out_dir, "world-notable", "2026.11", [notable_layer(places)], created=CREATED)
