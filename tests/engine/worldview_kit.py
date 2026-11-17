"""A tiny synthetic world with disputed areas, for the worldview tests: invented places in open
Pacific water, nothing real. The curated tables (placewise.constants.worldviews) are replaced by
TABLES for these tests.

            Nowhere Glacier (unit NWG, nobody's: answered as its holder XA)   lat 11 - 11.5
Alphaland (XA)            | Betaland (XB)               | Deltaland (XD)
North Province            |   North Strip (area: XA     |
                          |   claims it, XB holds it)   |
South Province            | East Region                 |
  Quiet Strip (area: XB claims it, XA holds it)         |   Odd Bit (area)
lon -150 .. -149          | -149 .. -148                | -148 .. -147         lat 10 - 11

Gammaland (XC, island, lat 12 - 12.5, lon -150 .. -149.5): its own country, merged into XA by
the XA view's table. Deltaland's view claims all of Betaland (a whole-country claim).
"""

import numpy as np
from lookup_kit import box_feature

from placewise.packs import LayerData, write_pack

CREATED = "2026-11-17T00:00:00Z"
VIEWS = ("xa", "xb", "xd")

TABLES = {
    "DE_FACTO_UNITS": {"NWG": "AAA"},
    "UNFLAGGED_HOLDERS": frozenset(),
    "VIEW_UNITS": {"XA": {"CCC": "AAA"}},
    "VIEW_ADMIN1": {
        "de_facto": {"Nowhere Glacier": "iso:XA-N"},
        "XA": {"North Strip": "iso:XA-N", "Nowhere Glacier": "iso:XA-N"},
    },
    "VIEW_AREA_NAMES": {"XA": {"North Strip": "Alpha North"}},
}

COUNTRIES = [
    # id, name, iso2, iso3, adm0_a3, sovereign, box, {view: adm0_a3}
    ("iso:XA", "Alphaland", "XA", "XAA", "AAA", "Alphaland", (10, -150, 11, -149), {}),
    ("iso:XB", "Betaland", "XB", "XBB", "BBB", "Betaland", (10, -149, 11, -148), {"xd": "DDD"}),
    ("iso:XD", "Deltaland", "XD", "XDD", "DDD", "Deltaland", (10, -148, 11, -147), {}),
    ("ne:NWG", "Nowhere Glacier", "", "", "NWG", "Nowhere", (11, -150, 11.5, -149.5),
     {"xa": "AAA", "xb": "BBB"}),
    ("iso:XC", "Gammaland", "XC", "XCC", "CCC", "Alphaland", (12, -150, 12.5, -149.5), {}),
]  # fmt: skip

ADMIN1 = [
    # id, name, country, adm0_a3, box
    ("iso:XA-N", "North Province", "XA", "AAA", (10.5, -150, 11, -149)),
    ("iso:XA-S", "South Province", "XA", "AAA", (10, -150, 10.5, -149)),
    ("iso:XB-E", "East Region", "XB", "BBB", (10, -149, 11, -148)),
    ("iso:XD-01", "Delta Province", "XD", "DDD", (10, -148, 11, -147)),
    ("ne:NWG+00?", "Glacier", "", "NWG", (11, -150, 11.5, -149.5)),
    ("iso:XC-01", "Gamma Island", "XC", "CCC", (12, -150, 12.5, -149.5)),
]

AREAS = [
    # id, name, holder adm0_a3, box, {view: adm0_a3}
    ("ne:1", "North Strip", "BBB", (10.8, -149, 11, -148), {"xa": "AAA", "xb": "BBB", "xd": "DDD"}),
    ("ne:2", "Quiet Strip", "AAA", (10, -149.3, 10.2, -149), {"xa": "AAA", "xb": "BBB", "xd": "AAA"}),
    ("ne:3", "Nowhere Glacier", "NWG", (11, -150, 11.5, -149.5), {"xa": "AAA", "xb": "BBB", "xd": "-99"}),
    ("ne:4", "Odd Bit", "DDD", (10, -147.2, 10.2, -147), {"xa": "B99", "xb": "DDD", "xd": "DDD"}),
]

CITIES = [
    # id, name, lat, lon, country
    ("geonames:1", "Alpha City", 10.75, -149.5, "XA"),
    ("geonames:2", "Beta Town", 10.4, -148.5, "XB"),
    ("geonames:3", "Strip Town", 10.9, -148.5, "XB"),
    ("geonames:4", "Delta Town", 10.5, -147.5, "XD"),
    ("geonames:5", "Gamma Port", 12.25, -149.75, "XC"),
]


def _countries():
    columns = {
        "id": [c[0] for c in COUNTRIES],
        "name": [c[1] for c in COUNTRIES],
        "iso2": [c[2] for c in COUNTRIES],
        "iso3": [c[3] for c in COUNTRIES],
        "adm0_a3": [c[4] for c in COUNTRIES],
        "sovereign": [c[5] for c in COUNTRIES],
    }
    for view in VIEWS:
        columns[f"adm0_a3_{view}"] = [c[7].get(view, c[4]) for c in COUNTRIES]
    features = [box_feature(*c[6], fid=c[0]) for c in COUNTRIES]
    types = {name: "str" for name in columns}
    return LayerData("countries", "polygon", columns, ("synthetic",), features=features, types=types)


def _admin1():
    columns = {
        "id": [a[0] for a in ADMIN1],
        "name": [a[1] for a in ADMIN1],
        "country": [a[2] for a in ADMIN1],
        "adm0_a3": [a[3] for a in ADMIN1],
    }
    features = [box_feature(*a[4], fid=a[0]) for a in ADMIN1]
    types = {name: "str" for name in columns}
    return LayerData("admin1", "polygon", columns, ("synthetic",), features=features, types=types)


def _areas():
    columns = {
        "id": [a[0] for a in AREAS],
        "name": [a[1] for a in AREAS],
        "adm0_a3": [a[2] for a in AREAS],
        "type": ["Disputed"] * len(AREAS),
    }
    for view in VIEWS:
        columns[f"adm0_a3_{view}"] = [a[4][view] for a in AREAS]
    features = [box_feature(*a[3], fid=a[0]) for a in AREAS]
    types = {name: "str" for name in columns}
    return LayerData("worldviews", "polygon", columns, ("synthetic",), features=features, types=types)


def _cities():
    columns = {
        "id": [c[0] for c in CITIES],
        "name": [c[1] for c in CITIES],
        "country": [c[4] for c in CITIES],
        "admin1": [""] * len(CITIES),
        "feature_code": ["PPLA"] * len(CITIES),
        "population": np.full(len(CITIES), 100_000, dtype=np.int64),
        "timezone": ["Pacific/Test"] * len(CITIES),
    }
    lat = np.array([c[2] for c in CITIES])
    lon = np.array([c[3] for c in CITIES])
    return LayerData("cities", "point", columns, ("synthetic",), lat=lat, lon=lon)


def write_world(out_dir):
    layers = [_countries(), _admin1(), _areas(), _cities()]
    return write_pack(out_dir, "world", "2026.11", layers, created=CREATED)
