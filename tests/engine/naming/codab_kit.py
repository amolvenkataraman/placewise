"""A synthetic world and three COD-AB packs for the COD-AB naming tests: invented boxes in open
Pacific water carrying the real packs' layer names, columns and id schemes (packbuild/codab.py).
The ISO codes are real so the rules recognise the countries; every place and coordinate is made up.

      lon 160 ............ 160.5 ........ 161 | 161 ......... 162 | 162 ........... 163
lat 21  "NP" (npl pack)                       | "LK" (lka pack)   | "BD" (bgd pack)
        P3 "Bagmati": district Kathmandu:     | Western: Colombo  | Dhaka: district Dhaka
        palikas Kathmandu | Lalitpur          | GN Fort | Pettah  | Khulna (no world match)
lat 20  (world admin1: one old zone "Bagmati")| (world: districts)| (world: Dhaka, Khulna Div.)
"""

import numpy as np

from placewise.model import Feature, Outline
from placewise.packs import LayerData, write_pack

CREATED = "2026-11-17T00:00:00Z"
VERSION = "2026.11"


def box(south, west, north, east):
    ring = ((south, west), (south, east), (north, east), (north, west))
    return Feature(outlines=(Outline((ring,)),))


def layer(name, rows, columns, source):
    data = {c: [r[1 + i] for r in rows] for i, c in enumerate(columns)}
    return LayerData(name, "polygon", data, (source,), features=[box(*r[0]) for r in rows])


COUNTRIES = [
    ((20, 160, 21, 161), "iso:NP", "Nepal", "NP", "NPL"),
    ((20, 161, 21, 162), "iso:LK", "Sri Lanka", "LK", "LKA"),
    ((20, 162, 21, 163), "iso:BD", "Bangladesh", "BD", "BGD"),
]
ADMIN1 = [
    ((20, 160, 21, 161), "iso:NP-BA", "Bagmati", "NP", "NPL"),  # the pre-2015 zone of the same name
    ((20, 161, 21, 162), "iso:LK-11", "Kolamba", "LK", "LKA"),  # a district, as Natural Earth has
    ((20.5, 162, 21, 163), "iso:BD-C", "Dhaka", "BD", "BGD"),
    ((20, 162, 20.5, 163), "iso:BD-D", "Khulna Division", "BD", "BGD"),
]
CITIES = [
    # id, name, lat, lon, country, population, feature_code
    ("geonames:1", "Kathmandu", 20.75, 160.25, "NP", 1_000_000, "PPLC"),
    ("geonames:2", "Thamel", 20.76, 160.26, "NP", 20_000, "PPLX"),
    ("geonames:3", "Patan", 20.75, 160.75, "NP", 200_000, "PPLA"),
    ("geonames:4", "Colombo", 20.5, 161.5, "LK", 650_000, "PPLC"),
    ("geonames:5", "Dhaka", 20.75, 162.5, "BD", 9_000_000, "PPLC"),
    ("geonames:6", "Khulna", 20.25, 162.5, "BD", 700_000, "PPLA"),
]


def write_world(out):
    countries = LayerData(
        "countries", "polygon",
        {"id": [c[1] for c in COUNTRIES], "name": [c[2] for c in COUNTRIES],
         "iso2": [c[3] for c in COUNTRIES], "iso3": [c[4] for c in COUNTRIES],
         "adm0_a3": [c[4] for c in COUNTRIES],
         "sovereign": [c[2] for c in COUNTRIES]},
        ("synthetic",), features=[box(*c[0]) for c in COUNTRIES],
    )  # fmt: skip
    admin1 = layer("admin1", ADMIN1, ("id", "name", "country", "adm0_a3"), "synthetic")
    cities = LayerData(
        "cities", "point",
        {"id": [c[0] for c in CITIES], "name": [c[1] for c in CITIES], "country": [c[4] for c in CITIES],
         "population": np.array([c[5] for c in CITIES], dtype=np.int64),
         "feature_code": [c[6] for c in CITIES],
         "timezone": ["Asia/Kathmandu"] * 3 + ["Asia/Colombo"] + ["Asia/Dhaka"] * 2},
        ("synthetic",), lat=np.array([c[2] for c in CITIES]), lon=np.array([c[3] for c in CITIES]),
    )  # fmt: skip
    return write_pack(out / "world", "world", VERSION, [countries, admin1, cities], created=CREATED)


COLUMNS = ("id", "name", "pcode", "parent", "type", "valid_on")


def rows(*items):
    """(box, pcode, name, parent pcode) -> layer rows in the COD-AB pack schema."""
    return [
        (b, f"codab:{p}", name, p, f"codab:{parent}" if parent else "", "", "2024-03-14")
        for b, p, name, parent in items
    ]


def write_npl(out):
    adm1 = rows(((20, 160, 21, 161), "NP03", "Bagmati", ""))
    adm2 = rows(((20, 160, 21, 161), "NP0327", "Kathmandu", "NP03"))
    adm3 = rows(
        ((20, 160, 21, 160.5), "NP0327301", "Kathmandu", "NP0327"),
        ((20, 160.5, 21, 160.99), "NP0327302", "Lalitpur", "NP0327"),  # a 1 km strip east of it is in none
    )
    layers = [layer(f"admin{n}", r, COLUMNS, "ocha-cod-ab-npl") for n, r in ((1, adm1), (2, adm2), (3, adm3))]
    return write_pack(out / "npl", "npl", VERSION, layers, created=CREATED)


def write_lka(out):
    adm1 = rows(((20, 161, 21, 162), "LK1", "Western", ""))
    adm2 = rows(((20, 161, 21, 162), "LK11", "Colombo", "LK1"))
    adm3 = rows(((20, 161, 21, 162), "LK1103", "Colombo", "LK11"))
    adm4 = rows(
        ((20, 161, 20.4, 162), "LK1103005", "Fort", "LK1103"),
        ((20.4, 161, 20.6, 162), "LK1103010", "Colombo", "LK1103"),  # named like the city: no sublocality
        ((20.6, 161, 21, 162), "LK1103015", "Pettah", "LK1103"),
    )
    layers = [
        layer(f"admin{n}", r, COLUMNS, "ocha-cod-ab-lka")
        for n, r in ((1, adm1), (2, adm2), (3, adm3), (4, adm4))
    ]
    return write_pack(out / "lka", "lka", VERSION, layers, created=CREATED)


def write_bgd(out):
    adm1 = rows(((20.5, 162, 21, 163), "BD30", "Dhaka", ""), ((20, 162, 20.5, 163), "BD40", "Khulna", ""))
    adm2 = rows(
        ((20.5, 162, 21, 163), "BD3026", "Dhaka", "BD30"), ((20, 162, 20.5, 163), "BD4047", "Khulna", "BD40")
    )
    adm3 = rows(
        ((20.5, 162, 21, 163), "BD30260001", "Dhaka South City Corporation", "BD3026"),
        ((20, 162, 20.5, 163), "BD40470001", "Khulna Sadar", "BD4047"),
    )
    layers = [layer(f"admin{n}", r, COLUMNS, "ocha-cod-ab-bgd") for n, r in ((1, adm1), (2, adm2), (3, adm3))]
    return write_pack(out / "bgd", "bgd", VERSION, layers, created=CREATED)


def write_all(out):
    return write_world(out), write_npl(out), write_lka(out), write_bgd(out)
