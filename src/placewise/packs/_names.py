"""Read a pack's name index (docs/pack-format.md, "Name index"): exact, prefix, fuzzy and code
lookups that answer with vectorised `Candidates`, and `resolve` from a candidate to its feature.

Every lookup normalises its text the way the writer did (`city_key` for names, `key` for codes),
so passing raw text or an already normalised key gives the same answer.
"""

from dataclasses import dataclass

import numpy as np

from placewise.model import BBox, Outline


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
    point layers.
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
    """One pack's name index (`Pack.names`). Arrays are memory-mapped on first use."""

    layers: tuple[str, ...]  # layer names; Candidates.layer indexes this

    def __init__(self, path, pack):
        raise NotImplementedError

    def __len__(self):
        """Number of entries (name and code variants) in the index."""
        raise NotImplementedError

    def exact(self, text, limit=None) -> Candidates:
        """Entries whose name key equals city_key(text), highest rank first."""
        raise NotImplementedError

    def prefix(self, text, limit=10) -> Candidates:
        """Up to `limit` features with a name key starting with city_key(text), highest rank first
        (one candidate per feature); match_score = len(query key) / len(matched key)."""
        raise NotImplementedError

    def fuzzy(self, text, limit=10) -> Candidates:
        """Up to `limit` features whose name key is near city_key(text) (trigram overlap, then
        Damerau-Levenshtein), best match_score first, then rank; one candidate per feature;
        match_score = 1 - edits / max(len(query key), len(key))."""
        raise NotImplementedError

    def codes(self, text) -> Candidates:
        """Entries whose code (IATA, ICAO, ISO, postal code, Wikidata QID, placewise id ...)
        equals key(text); "wikidata:Q42" also finds the bare QID. Exact only."""
        raise NotImplementedError

    def key(self, entry) -> str:
        """The normalised key of an entry (what it matched on)."""
        raise NotImplementedError

    def layer_kind(self, layer) -> str:
        """'point' or 'polygon' for a layer index or name."""
        raise NotImplementedError

    def resolve(self, layer, row) -> Resolved:
        """The feature at `row` of `layer` (an index into `layers`, or a layer name)."""
        raise NotImplementedError
