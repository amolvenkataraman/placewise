"""A tiny synthetic world for the search tests: invented places in open Pacific water (the lookup
tests' Alphaland), with name indexes. Nothing real, nothing personal.

world pack        countries, admin1 (North/South Province, West Region ...), GeoNames-like cities
                  (Alpha City, two Rivertons), an airport (XAI / XAAA) serving Alpha City
alpha pack        towns (Alpha City and Riverton as outlines), metros (Alpha City metro area),
                  parks (Alpha Falls National Park, code ALFA), lakes (Lake Alpha)
world-parks pack  park_points: Alpha Falls National Park again, as a point
"""

import difflib
import math

import numpy as np

from placewise.constants._keys import city_key, key
from placewise.constants.names import NAME_KINDS, PLACE_KINDS
from placewise.engine import Geocoder
from placewise.model import BBox
from placewise.packs import Candidates, LayerData, NameData, Resolved, open_pack, write_pack
from tests.engine.lookup_kit import CREATED, admin1_layer, box_feature, countries_layer

ALPHA_CITY_BOX = (0.70, -139.62, 0.80, -139.40)
SOUTH_RIVERTON_BOX = (0.20, -139.30, 0.25, -139.25)
PARK_BOX = (0.30, -139.95, 0.40, -139.70)

CITIES = [
    # id, name, lat, lon, country, population, feature_code
    ("geonames:1", "Alpha City", 0.75, -139.5, "XA", 1_000_000, "PPLC"),
    ("geonames:2", "Tinyville", 0.75, -139.35, "XA", 1_000, "PPL"),
    ("geonames:3", "Beta Town", 0.25, -138.97, "XB", 500_000, "PPLA"),
    ("geonames:4", "Riverton", 0.22, -139.27, "XA", 30_000, "PPL"),
    ("geonames:5", "Riverton", 0.50, -138.70, "XB", 5_000, "PPL"),
]


def _rank(population):
    return 0.3 + 0.07 * math.log10(population + 1)


def world_layers():
    cities = LayerData(
        "cities",
        "point",
        {
            "id": [c[0] for c in CITIES],
            "name": [c[1] for c in CITIES],
            "country": [c[4] for c in CITIES],
            "admin1": [""] * len(CITIES),
            "feature_code": [c[6] for c in CITIES],
            "population": np.array([c[5] for c in CITIES], dtype=np.int64),
            "timezone": ["Pacific/Alpha"] * len(CITIES),
        },
        ("synthetic",),
        lat=np.array([c[2] for c in CITIES]),
        lon=np.array([c[3] for c in CITIES]),
    )
    airports = LayerData(
        "airports",
        "point",
        {
            "id": ["ourairports:XAAA"],
            "name": ["Alpha International Airport"],
            "iata": ["XAI"],
            "icao": ["XAAA"],
            "type": ["large_airport"],
            "municipality": ["Tinyville"],  # its own town, not the city it serves
            "country": ["XA"],
            "region": ["XA-N"],
        },
        ("synthetic",),
        lat=np.array([0.70]),
        lon=np.array([-139.70]),
    )
    return [countries_layer(), admin1_layer(), cities, airports]


def world_names(layers):
    countries, admin1 = layers[:2]
    rows = []
    for i, name in enumerate(countries.columns["name"]):
        rows.append((name, "countries", i, "country", 0.9, "official"))
        for col in ("iso2", "iso3", "id"):
            rows.append((countries.columns[col][i], "countries", i, "country", 0.9, "code"))
    for i, name in enumerate(admin1.columns["name"]):
        rows.append((name, "admin1", i, "admin1", 0.75, "official"))
        code = f"{admin1.columns['country'][i]}-{admin1.columns['code'][i]}"
        rows += [
            (code, "admin1", i, "admin1", 0.75, "code"),
            (admin1.columns["id"][i], "admin1", i, "admin1", 0.75, "code"),
        ]
    for i, c in enumerate(CITIES):
        rows += [
            (c[1], "cities", i, "locality", _rank(c[5]), "official"),
            (c[0], "cities", i, "locality", _rank(c[5]), "code"),
        ]
    rows += [
        ("Alpha International Airport", "airports", 0, "airport", 0.5, "official"),
        ("XAI", "airports", 0, "airport", 0.5, "code"),
        ("XAAA", "airports", 0, "airport", 0.5, "code"),
        ("ourairports:XAAA", "airports", 0, "airport", 0.5, "code"),
    ]
    return rows


def alpha_layers():
    towns = LayerData(
        "towns",
        "polygon",
        {"id": ["town:alpha-city", "town:riverton"], "name": ["Alpha City", "Riverton"]},
        ("synthetic",),
        features=[box_feature(*ALPHA_CITY_BOX), box_feature(*SOUTH_RIVERTON_BOX)],
    )
    metros = LayerData(
        "metros",
        "polygon",
        {"id": ["metro:alpha-city"], "name": ["Alpha City"]},
        ("synthetic",),
        features=[box_feature(0.60, -139.75, 0.95, -139.30)],
    )
    parks = LayerData(
        "reserves",
        "polygon",
        {
            "id": ["parks:ALFA"],
            "name": ["Alpha Falls National Park"],
            "aliases": ["Alpha Falls"],
            "code": ["ALFA"],
            "tier": np.array([1], dtype=np.int64),
        },
        ("synthetic",),
        features=[box_feature(*PARK_BOX)],
    )
    lakes = LayerData(
        "waters",
        "polygon",
        {"id": ["lake:alpha"], "name": ["Lake Alpha"]},
        ("synthetic",),
        features=[box_feature(0.45, -139.50, 0.50, -139.40)],
    )
    return [towns, metros, parks, lakes]


ALPHA_NAMES = [
    ("Alpha City", "towns", 0, "locality", _rank(1_000_000), "official"),
    ("town:alpha-city", "towns", 0, "locality", _rank(1_000_000), "code"),
    ("Riverton", "towns", 1, "locality", _rank(30_000), "official"),
    ("town:riverton", "towns", 1, "locality", _rank(30_000), "code"),
    ("Alpha City", "metros", 0, "region", 0.75, "official"),
    ("metro:alpha-city", "metros", 0, "region", 0.75, "code"),
    ("Alpha Falls National Park", "reserves", 0, "park", 0.8, "official"),
    ("Alpha Falls", "reserves", 0, "park", 0.8, "alias"),
    ("ALFA", "reserves", 0, "park", 0.8, "code"),
    ("parks:ALFA", "reserves", 0, "park", 0.8, "code"),
    ("Lake Alpha", "waters", 0, "water", 0.6, "official"),
    ("lake:alpha", "waters", 0, "water", 0.6, "code"),
]


def parks_layers():
    return [
        LayerData(
            "park_spots",
            "point",
            {"id": ["wikidata:Q900001"], "name": ["Alpha Falls National Park"], "radius_km": np.array([5.0])},
            ("synthetic",),
            lat=np.array([0.35]),
            lon=np.array([-139.8]),
        )
    ]


PARKS_NAMES = [
    ("Alpha Falls National Park", "park_spots", 0, "park", 0.7, "official"),
    ("wikidata:Q900001", "park_spots", 0, "park", 0.7, "code"),
    ("Q900001", "park_spots", 0, "park", 0.7, "code"),
]


class FakeNameIndex:
    """The NameIndex interface (research SEARCH-INTERFACE.md) over a list of rows, in plain Python:
    exact, prefix, fuzzy (difflib), codes, key, layer_kind, resolve."""

    def __init__(self, pack, rows):
        self.pack = pack
        self.layers = tuple(dict.fromkeys(r[1] for r in rows))
        self.rows = rows
        self.keys = [key(r[0]) if r[5] == "code" else city_key(r[0]) for r in rows]

    def __len__(self):
        return len(self.rows)

    def _candidates(self, entries, scores):
        if not entries:
            return Candidates.empty()
        out = {f: [] for f in Candidates.__slots__}
        for e, s in zip(entries, scores, strict=True):
            _, layer, row, kind, rank, name_kind = self.rows[e]
            lat, lon, radius = self._where(layer, row)
            for f, v in (
                ("entry", e), ("layer", self.layers.index(layer)), ("row", row),
                ("kind", PLACE_KINDS.index(kind)),
                ("rank", rank), ("name_kind", NAME_KINDS.index(name_kind)), ("match_score", s), ("lat", lat),
                ("lon", lon), ("radius_km", radius),
            ):  # fmt: skip
                out[f].append(v)
        dtypes = dict(entry=np.int64, layer=np.int16, row=np.int64, kind=np.uint8, rank=np.float32,
                      name_kind=np.uint8, match_score=np.float32, lat=np.float64, lon=np.float64,
                      radius_km=np.float32)  # fmt: skip
        return Candidates(**{f: np.array(v, dtype=dtypes[f]) for f, v in out.items()})

    def _where(self, layer, row):
        lyr = self.pack[layer]
        if lyr.kind == "point":
            radius = lyr.value("radius_km", row) if "radius_km" in lyr.fields else 1.0
            return float(lyr.lat[row]), float(lyr.lon[row]), float(radius)
        s, w, n, e = lyr.bbox(row).as_tuple()
        lat, lon = (s + n) / 2, (w + e) / 2  # the kit's outlines are boxes: the centre is inside
        return lat, lon, float(np.hypot(n - lat, e - lon) * 111.2)

    def _by_rank(self, entries, scores=None):
        scores = scores or [1.0] * len(entries)
        pairs = sorted(zip(entries, scores, strict=True), key=lambda p: (-p[1], -self.rows[p[0]][4]))
        return self._candidates([p[0] for p in pairs], [p[1] for p in pairs])

    def exact(self, text, limit=None):
        k = city_key(text)
        found = [i for i, r in enumerate(self.rows) if r[5] != "code" and self.keys[i] == k]
        return self._by_rank(found[:limit] if limit else found)

    def prefix(self, text, limit=10):
        k = city_key(text)
        found = [i for i, r in enumerate(self.rows) if r[5] != "code" and self.keys[i].startswith(k)]
        return self._by_rank(found[:limit], [len(k) / len(self.keys[i]) for i in found[:limit]])

    def fuzzy(self, text, limit=10):
        k = city_key(text)
        scored = [
            (i, difflib.SequenceMatcher(None, k, self.keys[i]).ratio())
            for i, r in enumerate(self.rows)
            if r[5] != "code"
        ]
        scored = [p for p in scored if p[1] >= 0.75][:limit]
        return self._by_rank([p[0] for p in scored], [p[1] for p in scored])

    def codes(self, text):
        k = key(text)
        if k.startswith("wikidata:"):
            k = k.split(":", 1)[1]
        found = [i for i, r in enumerate(self.rows) if r[5] == "code" and self.keys[i] in (k, key(text))]
        return self._by_rank(found)

    def key(self, entry):
        return self.keys[int(entry)]

    def layer_kind(self, layer):
        name = self.layers[layer] if isinstance(layer, int | np.integer) else layer
        return self.pack[name].kind

    def resolve(self, layer, row, outlines=False):
        name = self.layers[layer] if isinstance(layer, int | np.integer) else layer
        lyr = self.pack[name]
        lat, lon, radius = self._where(name, row)
        columns = lyr.row(row)
        if lyr.kind == "point":
            box = BBox(lat - 0.01, lon - 0.01, lat + 0.01, lon + 0.01)
            parts = ()
        else:
            box = lyr.bbox(row)
            parts = lyr.feature(row).outlines if outlines else ()
        return Resolved(name, int(row), columns["id"], columns["name"], columns, lat, lon, radius, box, parts)


def _real_index(pack):
    try:
        index = pack.names
        index.exact("x")
        return index
    except (NotImplementedError, AttributeError, TypeError):
        return None


def write_packs(out_dir):
    """The three packs, opened, each with a name index (the real one when the reader has it)."""
    built = []
    for name, layers, rows in (
        ("world", world_layers(), None),
        ("alpha", alpha_layers(), ALPHA_NAMES),
        ("parkspots", parks_layers(), PARKS_NAMES),
    ):
        rows = rows if rows is not None else world_names(layers)
        try:
            path = write_pack(
                out_dir, name, "2026.11", layers, created=CREATED, names=NameData.from_rows(rows)
            )
        except NotImplementedError:
            path = write_pack(out_dir, name, "2026.11", layers, created=CREATED)
        pack = open_pack(path)
        if _real_index(pack) is None:
            pack.__dict__["names"] = FakeNameIndex(pack, rows)
        built.append(pack)
    return built


def geocoder(out_dir, overrides=None):
    return Geocoder(packs=write_packs(out_dir), overrides=overrides)


__all__ = ["ALPHA_CITY_BOX", "PARK_BOX", "SOUTH_RIVERTON_BOX", "geocoder", "write_packs"]
