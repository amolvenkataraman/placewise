"""A tiny synthetic world for the lookup tests: invented places in open Pacific water, nothing real.

Gammaland (XC, island)            lat 2.0 - 2.5, lon -140 .. -139.5
                                  (Alphaland's worldview column assigns it to XA)

Alphaland (XA)   | Betaland (XB)
North Province   | West Region | Zed Peninsula (id iso:XA-Z, administered by XB per the data)
-----------------|             |
South Province   |             |
lat 0 - 1, lon -140 .. -139 | -139 .. -138.5 | -138.5 .. -138
"""

import numpy as np

from placewise.model import Feature, Outline
from placewise.packs import LayerData, write_pack

CREATED = "2026-11-17T00:00:00Z"

VIEWS = ("xa", "xb", "un")

COUNTRIES = [
    # id, name, iso2, iso3, adm0_a3, sovereign, box, {view: adm0_a3}
    ("iso:XA", "Alphaland", "XA", "XAA", "XAA", "Alphaland", (0, -140, 1, -139), {"xa": "XAA", "xb": "XAA"}),
    ("iso:XB", "Betaland", "XB", "XBB", "XBB", "Betaland", (0, -139, 1, -138), {"xa": "XBB", "xb": "XBB"}),
    (
        "iso:XC",
        "Gammaland",
        "XC",
        "XCC",
        "XCC",
        "Gammaland",
        (2, -140, 2.5, -139.5),
        {"xa": "XAA", "xb": "XCC"},
    ),
]

ADMIN1 = [
    # id, name, country, code, adm0_a3, box
    ("iso:XA-N", "North Province", "XA", "N", "XAA", (0.5, -140, 1, -139)),
    ("iso:XA-S", "South Province", "XA", "S", "XAA", (0, -140, 0.5, -139)),
    ("iso:XB-W", "West Region", "XB", "W", "XBB", (0, -139, 1, -138.5)),
    ("iso:XA-Z", "Zed Peninsula", "XB", "Z", "XBB", (0, -138.5, 1, -138)),
    ("iso:XC-01", "Gamma Island", "XC", "01", "XCC", (2, -140, 2.5, -139.5)),
]

CITIES = [
    # id, name, lat, lon, country, population, feature_code, timezone
    ("geonames:1", "Alpha City", 0.75, -139.5, "XA", 1_000_000, "PPLC", "Pacific/Alpha"),
    ("geonames:2", "Tinyville", 0.75, -139.35, "XA", 1_000, "PPL", "Pacific/Alpha"),
    ("geonames:3", "Beta Town", 0.25, -138.97, "XB", 500_000, "PPLA", "Pacific/Beta"),
    ("geonames:4", "Southby", 0.2, -139.2, "XA", 2_000, "PPL", "Pacific/Alpha"),
    ("geonames:5", "Gamma Port", 2.25, -139.75, "XC", 20_000, "PPLA", "Pacific/Gamma"),
    ("geonames:6", "Zed Harbour", 0.5, -138.05, "XA", 300_000, "PPLA", "Pacific/Zed"),
    ("geonames:7", "Northam", 0.53, -139.8, "XA", 50_000, "PPL", "Pacific/Alpha"),
    ("geonames:8", "Southam", 0.45, -139.8, "XA", 50_000, "PPL", "Pacific/Alpha"),
    ("geonames:9", "Alpha Docks", 0.77, -139.5, "XA", 400_000, "PPLX", "Pacific/Alpha"),  # a city section
]

AIRPORTS = [
    # id, name, lat, lon, iata, icao, country, region
    ("ourairports:XAAA", "Alpha International", 0.70, -139.60, "XAI", "XAAA", "XA", "XA-N"),
]


def box_feature(south, west, north, east, fid=None):
    """A counter-clockwise box."""
    ring = ((south, west), (south, east), (north, east), (north, west))
    return Feature(outlines=(Outline((ring,)),), id=fid)


def countries_layer():
    columns = {
        "id": [c[0] for c in COUNTRIES],
        "name": [c[1] for c in COUNTRIES],
        "iso2": [c[2] for c in COUNTRIES],
        "iso3": [c[3] for c in COUNTRIES],
        "adm0_a3": [c[4] for c in COUNTRIES],
        "sovereign": [c[5] for c in COUNTRIES],
        "type": ["Sovereign country"] * len(COUNTRIES),
        "population": [1000] * len(COUNTRIES),
    }
    for view in VIEWS:
        columns[f"adm0_a3_{view}"] = [c[7].get(view, "-99") for c in COUNTRIES]
        columns[f"fclass_{view}"] = ["Admin-0 country"] * len(COUNTRIES)
    features = [box_feature(*c[6], fid=c[0]) for c in COUNTRIES]
    return LayerData("countries", "polygon", columns, ("synthetic",), features=features)


def admin1_layer():
    columns = {
        "id": [a[0] for a in ADMIN1],
        "name": [a[1] for a in ADMIN1],
        "country": [a[2] for a in ADMIN1],
        "code": [a[3] for a in ADMIN1],
        "adm0_a3": [a[4] for a in ADMIN1],
        "type_en": ["Province"] * len(ADMIN1),
    }
    features = [box_feature(*a[5], fid=a[0]) for a in ADMIN1]
    return LayerData("admin1", "polygon", columns, ("synthetic",), features=features)


def cities_layer():
    columns = {
        "id": [c[0] for c in CITIES],
        "name": [c[1] for c in CITIES],
        "country": [c[4] for c in CITIES],
        "admin1": [""] * len(CITIES),
        "feature_code": [c[6] for c in CITIES],
        "population": np.array([c[5] for c in CITIES], dtype=np.int64),
        "timezone": [c[7] for c in CITIES],
    }
    lat = np.array([c[2] for c in CITIES])
    lon = np.array([c[3] for c in CITIES])
    return LayerData("cities", "point", columns, ("synthetic",), lat=lat, lon=lon)


def airports_layer():
    columns = {
        "id": [a[0] for a in AIRPORTS],
        "name": [a[1] for a in AIRPORTS],
        "iata": [a[4] for a in AIRPORTS],
        "icao": [a[5] for a in AIRPORTS],
        "type": ["large_airport"] * len(AIRPORTS),
        "country": [a[6] for a in AIRPORTS],
        "region": [a[7] for a in AIRPORTS],
    }
    lat = np.array([a[2] for a in AIRPORTS])
    lon = np.array([a[3] for a in AIRPORTS])
    return LayerData("airports", "point", columns, ("synthetic",), lat=lat, lon=lon)


def write_world(out_dir):
    """The synthetic pack, named and versioned like the real one: world-2026.11."""
    layers = [countries_layer(), admin1_layer(), cities_layer(), airports_layer()]
    return write_pack(out_dir, "world", "2026.11", layers, created=CREATED)
