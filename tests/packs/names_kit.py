"""A small synthetic pack with a name index, for tests of the name index and of forward search.
Invented places with real-looking names on made-up coordinates: nothing personal."""

import numpy as np
from pack_kit import CREATED, box_feature

from placewise.model import Feature, Outline
from placewise.packs import LayerData, NameData, open_pack, write_pack

# (name, aliases, population, lat, lon)
CITIES = (
    ("Springfield", "", 170_000, 37.2, -93.3),
    ("Springfield", "", 115_000, 39.8, -89.6),
    ("Toronto", "Hogtown|T.O.", 2_800_000, 43.65, -79.38),
    ("Mississauga", "", 720_000, 43.59, -79.64),
    ("Mumbai", "Bombay", 12_400_000, 19.07, 72.88),
    ("Saint Paul", "", 300_000, 44.95, -93.09),
    ("Paris", "", 2_100_000, 48.86, 2.35),
    ("Paris", "", 25_000, 33.66, -95.55),
)
# (name, code, south, west, north, east)
ADMIN = (
    ("Ontario", "CA-ON", 42.0, -95.0, 56.0, -74.0),
    ("Missouri", "US-MO", 36.0, -95.7, 40.6, -89.1),
)


def _l_shape(south, west, north, east):
    """An L whose bbox centre is outside it, so an inside point must be computed."""
    mid_lat, mid_lon = (south + north) / 2, (west + east) / 2
    ring = (
        (south, west),
        (south, east),
        (mid_lat, east),
        (mid_lat, mid_lon),
        (north, mid_lon),
        (north, west),
    )
    return Feature(outlines=(Outline((ring,)),))


def names_layers():
    lat = np.array([c[3] for c in CITIES])
    lon = np.array([c[4] for c in CITIES])
    cities = LayerData(
        name="cities",
        kind="point",
        columns={
            "id": [f"synthetic:city:{i}" for i in range(len(CITIES))],
            "name": [c[0] for c in CITIES],
            "aliases": [c[1] for c in CITIES],
            "population": np.array([c[2] for c in CITIES], dtype=np.int64),
        },
        sources=("synthetic",),
        lat=lat,
        lon=lon,
    )
    admin = LayerData(
        name="admin1",
        kind="polygon",
        columns={
            "id": [f"iso:{a[1]}" for a in ADMIN],
            "name": [a[0] for a in ADMIN],
            "code": [a[1] for a in ADMIN],
        },
        sources=("synthetic",),
        features=[box_feature(*a[2:]) for a in ADMIN],
    )
    parks = LayerData(
        name="parks",
        kind="polygon",
        columns={
            "id": ["synthetic:park:0"],
            "name": ["Yosemite National Park"],
            "aliases": ["Yosemite"],
            "code": ["YOSE"],
            "area_km2": np.array([3_000.0]),
        },
        sources=("synthetic",),
        features=[_l_shape(37.5, -120.0, 38.2, -119.2)],
    )
    airports = LayerData(
        name="airports",
        kind="point",
        columns={
            "id": ["synthetic:airport:0"],
            "name": ["Toronto Pearson International Airport"],
            "iata": ["YYZ"],
            "icao": ["CYYZ"],
        },
        sources=("synthetic",),
        lat=np.array([43.68]),
        lon=np.array([-79.63]),
    )
    return [cities, admin, parks, airports]


def names_data(layers):
    """NameData for names_layers(), written out by hand (packbuild.names.build does it by spec)."""
    cities, admin = layers[:2]
    rows = []
    for i, (name, aliases, population, _, _) in enumerate(CITIES):
        rank = 0.3 + 0.7 * min(np.log10(population + 1) / 9, 1)
        rows.append((name, "cities", i, "locality", rank, "official"))
        rows += [(a, "cities", i, "locality", rank, "alias") for a in aliases.split("|") if a]
        rows.append((cities.columns["id"][i], "cities", i, "locality", rank, "code"))
    for i, a in enumerate(ADMIN):
        rows += [(a[0], "admin1", i, "admin1", 0.8, "official"), (a[1], "admin1", i, "admin1", 0.8, "code")]
        rows.append((admin.columns["id"][i], "admin1", i, "admin1", 0.8, "code"))
    rows += [
        ("Yosemite National Park", "parks", 0, "park", 0.8, "official"),
        ("Yosemite", "parks", 0, "park", 0.8, "alias"),
        ("YOSE", "parks", 0, "park", 0.8, "code"),
        ("synthetic:park:0", "parks", 0, "park", 0.8, "code"),
        ("Toronto Pearson International Airport", "airports", 0, "airport", 0.6, "official"),
        ("YYZ", "airports", 0, "airport", 0.6, "code"),
        ("CYYZ", "airports", 0, "airport", 0.6, "code"),
    ]
    return NameData.from_rows(rows)


def names_pack(tmp_path, name="names-test"):
    """Write the synthetic pack with its name index and open it."""
    layers = names_layers()
    path = write_pack(tmp_path, name, "2026.11", layers, created=CREATED, names=names_data(layers))
    return open_pack(path)
