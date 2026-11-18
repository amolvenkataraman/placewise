"""Read a pack's name index (docs/pack-format.md, "Name index"): exact, prefix, fuzzy and code
lookups that answer with vectorised `Candidates`, and `resolve` from a candidate to its feature.

Every lookup normalises its text the way the writer did (`city_key` for names, `key` for codes),
so passing raw text or an already normalised key gives the same answer.
"""

import bisect
import json
import math
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np

from placewise.constants import names as nc
from placewise.constants._keys import city_key, key
from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo import normalize_lon
from placewise.model import BBox, Outline

from . import _geometry as gm
from ._name_match import IdView, KeyTable, Trigrams, ranges

# prefix lookups over many entries rank only the best `limit` x this by rank
_PREFIX_POOL = 8
_WIKIDATA = re.compile(r"^wikidata:(Q\d+)$", re.IGNORECASE)
_KM_PER_DEGREE = math.pi * MEAN_RADIUS_KM / 180


@dataclass(frozen=True, slots=True, eq=False)
class Candidates:
    """Matches from one pack's name index, one element per (matched name, feature), best first.

    Arrays, all the same length:
      entry       int64    the matched entry in its NameIndex (NameIndex.key(entry) is its key)
      layer       int16    index into NameIndex.layers
      row         int64    the feature's row in that layer
      kind        uint8    index into placewise.constants.names.PLACE_KINDS (PlaceKind values)
      rank        float32  prior prominence in [0, 1] (population, area, tier, fame), higher first
      name_kind   uint8    index into placewise.constants.names.NAME_KINDS (official, alias ...)
      match_score float32  how well the text matched, in (0, 1]: 1 for exact and code matches
      lat, lon    float64  a point of the feature: the point itself for point layers, a point
                           guaranteed inside it for polygon layers (as Resolved.lat/lon)
      radius_km   float32  the feature's size around that point (as Resolved.radius_km)
    """

    entry: np.ndarray
    layer: np.ndarray
    row: np.ndarray
    kind: np.ndarray
    rank: np.ndarray
    name_kind: np.ndarray
    match_score: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    radius_km: np.ndarray

    def __len__(self):
        return len(self.entry)

    @classmethod
    def empty(cls):
        return cls(
            entry=np.zeros(0, np.int64),
            layer=np.zeros(0, np.int16),
            row=np.zeros(0, np.int64),
            kind=np.zeros(0, np.uint8),
            rank=np.zeros(0, np.float32),
            name_kind=np.zeros(0, np.uint8),
            match_score=np.zeros(0, np.float32),
            lat=np.zeros(0, np.float64),
            lon=np.zeros(0, np.float64),
            radius_km=np.zeros(0, np.float32),
        )

    def take(self, index):
        """The candidates at `index` (an int array or boolean mask), in that order."""
        return Candidates(**{f: getattr(self, f)[index] for f in self.__slots__})


@dataclass(frozen=True, slots=True)
class Resolved:
    """A candidate's feature, ready to become an Entity.

    `lat`, `lon` is the point itself for point layers and, for polygon layers, a point guaranteed
    to be inside the feature (its label point when that is inside, else one computed at build
    time). `radius_km`: polygon layers, the farthest outline vertex from that point; point layers,
    the layer's radius column (`radius_km`, `radius_m`), else a disc for its population, else a
    default. `bbox`: the feature's box; for points, the point's disc. `outlines` is empty for
    point layers and unless resolve() was asked for them.
    """

    layer: str
    row: int
    id: str
    name: str
    columns: dict
    lat: float
    lon: float
    radius_km: float
    bbox: BBox
    outlines: tuple[Outline, ...] = ()


class NameIndex:
    """One pack's name index (`Pack.names`). Arrays are memory-mapped on first use; the fuzzy
    trigram index is built in memory on the first fuzzy lookup."""

    def __init__(self, path, pack):
        self.path = Path(path)
        self._pack = pack
        meta = json.loads((self.path / nc.NAMES_JSON).read_text(encoding="utf-8"))
        if meta.get("format") != nc.NAMES_FORMAT:
            raise ValueError(f"{self.path}: name index format {meta.get('format')} is not supported")
        self.meta = meta
        self.layers = tuple(meta["layers"])  # Candidates.layer indexes this
        self._kind_codes = np.array([nc.PLACE_KINDS.index(k) for k in meta["kinds"]], dtype=np.uint8)
        self._arrays = {}
        self._located = {}

    def __len__(self):
        """Number of entries (name and code variants) in the index."""
        return int(self.meta["entries"])

    def __repr__(self):
        return f"<NameIndex {self._pack.name}: {len(self)} entries>"

    # --- lookups --------------------------------------------------------------------------------

    def exact(self, text, limit=None) -> Candidates:
        """Entries whose name key equals city_key(text), highest rank first."""
        k = self._names.find(city_key(text))
        if k < 0:
            return Candidates.empty()
        start, stop = self._names.entries(k, k + 1)
        if limit is not None:
            stop = min(stop, start + max(int(limit), 0))
        return self._candidates(np.arange(start, stop, dtype=np.int64), 1.0)

    def prefix(self, text, limit=10) -> Candidates:
        """Up to `limit` features with a name key starting with city_key(text), highest rank first
        (one candidate per feature); match_score = len(query key) / len(matched key)."""
        q = city_key(text)
        if not q or limit <= 0:
            return Candidates.empty()
        lo, hi = self._names.prefix_range(q)
        start, stop = self._names.entries(lo, hi)
        entry = np.arange(start, stop, dtype=np.int64)
        rank = self._array("rank")
        pool = limit * _PREFIX_POOL
        if len(entry) > pool:
            entry = np.sort(entry[np.argpartition(-rank[entry], pool)[:pool]])
        lengths = self._names.entry_lengths(entry)
        score = np.minimum(len(q.encode("utf-8")) / np.maximum(lengths, 1), 1.0)
        return self._best_per_feature(entry, score, limit, by_score=False)

    def fuzzy(self, text, limit=10) -> Candidates:
        """Up to `limit` features whose name key is near city_key(text) (trigram overlap, then
        Damerau-Levenshtein), best match_score first, then rank; one candidate per feature;
        match_score = 1 - edits / max(len(query key), len(key))."""
        q = city_key(text)
        if not q or limit <= 0 or not len(self._names):
            return Candidates.empty()
        keys, score = self._trigrams.near(q, self._names)
        if not len(keys):
            return Candidates.empty()
        start = self._names.start
        counts = start[keys + 1] - start[keys]
        entry = ranges(start[keys], start[keys + 1])
        return self._best_per_feature(entry, np.repeat(score, counts), limit, by_score=True)

    def codes(self, text) -> Candidates:
        """Entries whose code (IATA, ICAO, ISO, postal code, Wikidata QID, park code ...) equals
        key(text), and rows whose id equals text; "wikidata:Q42" also finds the bare QID. Exact
        only, highest rank first, one candidate per feature."""
        text = str(text).strip()
        found = []
        for variant in dict.fromkeys([text, *_WIKIDATA.findall(text)]):
            k = self._codes.find(key(variant))
            if k >= 0:
                found.append(np.arange(*self._codes.entries(k, k + 1), dtype=np.int64))
        by_id = self._by_id(text)
        entry = np.concatenate([*found, by_id]) if found or len(by_id) else np.zeros(0, np.int64)
        if not len(entry):
            return Candidates.empty()
        code = np.full(len(entry), nc.CODE, dtype=np.uint8)
        return self._best_per_feature(entry, np.ones(len(entry)), len(entry), by_score=False, name_kind=code)

    def key(self, entry) -> str:
        """The normalised key of an entry (what it matched on)."""
        entry = int(entry)
        table = self._names if entry < self._names.start[-1] else self._codes
        k = int(np.searchsorted(table.start, entry, side="right")) - 1
        return table[k].decode("utf-8")

    # --- features -------------------------------------------------------------------------------

    def layer_kind(self, layer) -> str:
        """'point' or 'polygon' for a layer index or name."""
        return self._pack[self._layer_name(layer)].kind

    def resolve(self, layer, row, outlines=False) -> Resolved:
        """The feature at `row` of `layer` (an index into `layers`, or a layer name); its
        outlines only when asked (building them costs time for big polygons)."""
        name = self._layer_name(layer)
        data = self._pack[name]
        row = int(row)
        columns = data.row(row)
        (lat,), (lon,), (radius,) = self._locate(np.array([self.layers.index(name)]), np.array([row]))
        lat, lon, radius = float(lat), float(lon), float(radius)
        if data.kind == "polygon":
            bbox = data.bbox(row)
            shapes = data.feature(row).outlines if outlines else ()
        else:
            bbox, shapes = _disc_bbox(lat, lon, radius), ()
        return Resolved(
            layer=name,
            row=row,
            id=columns.get("id") or "",
            name=columns.get("name") or "",
            columns=columns,
            lat=lat,
            lon=lon,
            radius_km=radius,
            bbox=bbox,
            outlines=tuple(shapes),
        )

    # --- internals ------------------------------------------------------------------------------

    def _layer_name(self, layer):
        if isinstance(layer, str):
            if layer not in self.layers:
                raise KeyError(f"the name index of {self._pack.name!r} has no layer {layer!r}")
            return layer
        return self.layers[int(layer)]

    def _array(self, rel):
        if rel not in self._arrays:
            self._arrays[rel] = np.load(self.path / f"{rel}.npy", mmap_mode="r", allow_pickle=False)
        return self._arrays[rel]

    @cached_property
    def _names(self):
        return KeyTable(self.path, "name")

    @cached_property
    def _codes(self):
        return KeyTable(self.path, "code")

    @cached_property
    def _trigrams(self):
        return Trigrams.build(self._names)

    def _by_id(self, text):
        """Best entries of the rows whose id is exactly `text`, in every indexed layer."""
        found = []
        for name in self.layers:
            layer = self._pack[name]
            order = self._array(f"ids/{name}")
            ids = IdView(layer, order)
            i = bisect.bisect_left(ids, text)
            if i < len(ids) and ids[i] == text:
                entry = int(self._array(f"entry/{name}")[order[i]])
                if entry >= 0:
                    found.append(entry)
        return np.array(found, dtype=np.int64)

    def _best_per_feature(self, entry, score, limit, by_score, name_kind=None):
        """One candidate per feature, ordered by rank (or by score, then rank), at most `limit`."""
        layer = self._array("layer")[entry].astype(np.int64)
        row = self._array("row")[entry].astype(np.int64)
        rank = self._array("rank")[entry]
        order = np.lexsort((entry, -rank, -score) if by_score else (entry, -score, -rank))
        _, first = np.unique((layer << 32 | row)[order], return_index=True)
        order = order[np.sort(first)][:limit]
        kinds = None if name_kind is None else name_kind[order]
        return self._candidates(entry[order], score[order], name_kind=kinds)

    def _candidates(self, entry, score, name_kind=None):
        layer = self._array("layer")[entry].astype(np.int16)
        row = self._array("row")[entry].astype(np.int64)
        lat, lon, radius = self._locate(layer, row)
        return Candidates(
            entry=entry.astype(np.int64),
            layer=layer,
            row=row,
            kind=self._kind_codes[self._array("kind")[entry]],
            rank=np.asarray(self._array("rank")[entry], dtype=np.float32),
            name_kind=np.asarray(self._array("name_kind")[entry] if name_kind is None else name_kind, "u1"),
            match_score=np.broadcast_to(np.asarray(score, dtype=np.float32), entry.shape).copy(),
            lat=lat,
            lon=lon,
            radius_km=radius,
        )

    def _locate(self, layer, row):
        lat, lon = np.empty(len(row)), np.empty(len(row))
        radius = np.empty(len(row), dtype=np.float32)
        for code in np.unique(layer).tolist():
            at = np.flatnonzero(layer == code)
            g_lat, g_lon, g_radius = self._geometry(self.layers[code])
            lat[at], lon[at], radius[at] = g_lat[row[at]], g_lon[row[at]], g_radius[row[at]]
        return lat, lon, radius

    def _geometry(self, name):
        """(lat, lon, radius_km) arrays for every row of a layer, cached."""
        if name not in self._located:
            self._located[name] = self._layer_geometry(self._pack[name])
        return self._located[name]

    def _layer_geometry(self, layer):
        name = layer.name
        if layer.kind == "polygon":
            point = gm.from_e7(self._array(f"inside/{name}"))
            return point[:, 0], point[:, 1], np.asarray(self._array(f"radius/{name}"), dtype=np.float32)
        return layer.lat, layer.lon, _point_radius(layer)


def _point_radius(layer):
    """Radius (km) of each point: the radius column, else a disc for the population, else the
    default; zero, negative or null values count as unknown."""
    n = layer.count
    radius = np.full(n, np.nan)
    for field, scale in (("radius_km", 1.0), ("radius_m", 1e-3)):
        if field in layer.fields and layer.fields[field] != "str":
            values = np.asarray(layer.column(field), dtype=np.float64) * scale
            radius = np.where(np.isnan(radius) & (values > 0), values, radius)
    if "population" in layer.fields and layer.fields["population"] != "str":
        people = np.asarray(layer.column("population"), dtype=np.float64)
        disc = np.sqrt(np.maximum(people, 0) / nc.POINT_DENSITY_PER_KM2 / math.pi)
        disc = np.clip(disc, nc.POINT_MIN_RADIUS_KM, nc.POINT_MAX_RADIUS_KM)
        radius = np.where(np.isnan(radius) & (people > 0), disc, radius)
    return np.where(np.isnan(radius), nc.POINT_DEFAULT_RADIUS_KM, radius).astype(np.float32)


def _disc_bbox(lat, lon, radius_km):
    """The box around a disc; west > east when it crosses the antimeridian."""
    dlat = radius_km / _KM_PER_DEGREE
    south, north = max(lat - dlat, -90.0), min(lat + dlat, 90.0)
    cos = math.cos(math.radians(lat))
    if north >= 90 or south <= -90 or cos * 180 <= dlat:
        return BBox(south, -180.0, north, 180.0)
    dlon = dlat / cos
    return BBox(south, float(normalize_lon(lon - dlon)), north, float(normalize_lon(lon + dlon)))
