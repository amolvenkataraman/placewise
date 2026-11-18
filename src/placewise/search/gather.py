"""Gathering candidates from every open pack's name index into one Pool (struct of arrays).

Each lookup's Candidates join the pool tagged with the pack they came from, whether they were a
fuzzy match, the context group they must sit in (-1: none; see rank.context_factors) and a factor
(city aliases, override rules)."""

from dataclasses import dataclass

import numpy as np

_FIELDS = ("entry", "layer", "row", "kind", "rank", "name_kind", "match_score", "lat", "lon", "radius_km")


@dataclass(frozen=True, slots=True, eq=False)
class Pool:
    pack: np.ndarray
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
    fuzzy: np.ndarray
    prefix: np.ndarray
    group: np.ndarray
    factor: np.ndarray

    def __len__(self):
        return len(self.pack)

    def take(self, index):
        return Pool(**{f: getattr(self, f)[index] for f in self.__slots__})


class Gatherer:
    """Collects Candidates from the indexes: a list of (pack position, Pack, NameIndex)."""

    def __init__(self, indexes):
        self.indexes = indexes
        self.parts = []

    def add(self, pack, found, *, fuzzy=False, prefix=False, group=-1, factor=1.0, kinds=None):
        """Add `found` (Candidates) from pack position `pack`; `kinds` (PLACE_KINDS indexes) keeps
        only candidates of those kinds."""
        if kinds is not None and len(found):
            found = found.take(np.flatnonzero(np.isin(np.asarray(found.kind), list(kinds))))
        if not len(found):
            return
        n = len(found)
        part = {f: np.asarray(getattr(found, f)) for f in _FIELDS}
        part["pack"] = np.full(n, pack, dtype=np.int64)
        part["fuzzy"] = np.full(n, fuzzy, dtype=bool)
        part["prefix"] = np.full(n, prefix, dtype=bool)
        part["group"] = np.full(n, group, dtype=np.int64)
        part["factor"] = np.full(n, factor, dtype=np.float64)
        self.parts.append(part)

    def each(self, method, *args, **options):
        """Ask every index `method(*args)` and add the answers with `options`."""
        for pos, _, index in self.indexes:
            self.add(pos, getattr(index, method)(*args), **options)

    def ids(self, ident, factor=1.0):
        """Every feature whose placewise id is `ident` (ids are codes of their own row)."""
        from placewise.constants.names import CODE

        for pos, pack, index in self.indexes:
            found = index.codes(ident)
            if len(found):
                keep = np.asarray(found.name_kind) == CODE
                rows = [i for i in np.flatnonzero(keep) if _row_id(pack, index, found, i) == ident]
                self.add(pos, found.take(np.asarray(rows, dtype=np.int64)), factor=factor)

    def best_prior(self):
        return max((float(p["rank"].max()) for p in self.parts), default=-1.0)

    def pool(self):
        if not self.parts:
            ints = {"pack", "entry", "layer", "row", "kind", "name_kind", "group"}
            return Pool(
                **{
                    f: np.zeros(
                        0, dtype=np.int64 if f in ints else bool if f in ("fuzzy", "prefix") else np.float64
                    )
                    for f in Pool.__slots__
                }
            )
        return Pool(**{f: np.concatenate([p[f] for p in self.parts]) for f in Pool.__slots__})


def _row_id(pack, index, found, i):
    return pack[index.layers[int(found.layer[i])]].value("id", int(found.row[i]))
