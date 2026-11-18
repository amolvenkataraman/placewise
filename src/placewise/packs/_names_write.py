"""Write a pack's name index (docs/pack-format.md, "Name index") from `NameData`.

`prepare` validates and computes everything (keys, sort orders, inside points) before the pack
writer touches the disk; `write` puts the result in `names/`.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from placewise.constants import names as nc
from placewise.constants._keys import city_key, key

from . import _inside


@dataclass
class NameData:
    """Names to index, for write_pack(..., names=NameData(...)): one row per (text, feature).

    text       the name or code as written; the writer normalises it (city_key for names, key for
               codes), so every reader lookup compares like with like
    layer      the layer name of the feature
    row        the feature's row in that layer
    kind       a PlaceKind value ("locality", "park" ...)
    rank       prior prominence in [0, 1], higher first
    name_kind  one of placewise.constants.names.NAME_KINDS ("official", "alias", "code" ...);
               "code" entries are matched exactly by NameIndex.codes, the rest by name
    points     optional label points per polygon layer, {layer: (lat, lon)} arrays of the layer's
               length (NaN where none): used as the feature's inside point when they are inside it

    Every indexed layer's `id` column is indexed too (NameIndex.codes finds rows by id), so ids
    need no entries of their own.
    """

    text: Sequence[str]
    layer: Sequence[str]
    row: Sequence[int]
    kind: Sequence[str]
    rank: Sequence[float]
    name_kind: Sequence[str]
    points: dict = field(default_factory=dict)

    @classmethod
    def from_rows(cls, rows, points=None):
        """From (text, layer, row, kind, rank, name_kind) tuples: the small-index builder for tests."""
        rows = list(rows)
        columns = list(zip(*rows, strict=True)) if rows else [()] * 6
        return cls(*columns, points=dict(points or {}))

    def __len__(self):
        return len(self.text)


@dataclass
class _Table:
    """Distinct sorted keys and, per key, its slice of the entry arrays."""

    blob: bytes
    offsets: np.ndarray  # int32, keys + 1
    start: np.ndarray  # int32, keys + 1: entries of key k are start[k]:start[k + 1]


@dataclass
class Plan:
    """A validated name index, ready to write."""

    meta: dict
    names: _Table
    codes: _Table
    entries: dict  # file stem -> array
    per_layer: dict  # (subdir, layer) -> array


def prepare(data, layers):
    """Validate `data` against the prepared layers ({name: _Prepared}) and compute the index."""
    n = len(data.text)
    columns = ("layer", "row", "kind", "rank", "name_kind")
    if any(len(getattr(data, c)) != n for c in columns):
        raise ValueError("names: text, layer, row, kind, rank and name_kind need the same length")
    order = list(dict.fromkeys(data.layer))
    if unknown := [name for name in order if name not in layers]:
        raise ValueError(f"names: unknown layer(s) {', '.join(map(repr, unknown))}")
    layer_code = {name: i for i, name in enumerate(order)}
    layer = np.fromiter((layer_code[x] for x in data.layer), dtype=np.int64, count=n)
    row = np.asarray(data.row, dtype=np.int64).reshape(n)
    counts = np.array([layers[name].count for name in order], dtype=np.int64)
    if n and ((row < 0) | (row >= counts[layer])).any():
        raise ValueError("names: a row is out of range for its layer")
    kind = _codes(data.kind, nc.PLACE_KINDS, "kind")
    name_kind = _codes(data.name_kind, nc.NAME_KINDS, "name_kind")
    rank = np.asarray(data.rank, dtype=np.float64).reshape(n)
    if n and not (np.isfinite(rank).all() and (rank >= 0).all() and (rank <= 1).all()):
        raise ValueError("names: every rank must be in [0, 1]")
    is_code = name_kind == nc.CODE
    keys = np.empty(n, dtype=object)
    keys[:] = [key(t) if c else city_key(t) for t, c in zip(data.text, is_code, strict=True)]
    uniq, key_id = np.unique(keys, return_inverse=True) if n else (keys, np.zeros(0, np.int64))
    key_id = key_id.reshape(n)
    keep = np.flatnonzero(keys != "") if n else np.zeros(0, dtype=np.int64)

    # one entry per (table, key, feature): the best name kind, then the highest rank
    by = (-rank[keep], name_kind[keep], row[keep], layer[keep], key_id[keep], is_code[keep])
    keep = keep[np.lexsort(by)]
    same = np.stack([is_code[keep], key_id[keep], layer[keep], row[keep]])
    first = np.ones(len(keep), dtype=bool)
    first[1:] = (same[:, 1:] != same[:, :-1]).any(axis=0)
    keep = keep[first]
    # within a key: highest rank first, then layer and row, so the order is reproducible
    keep = keep[np.lexsort((row[keep], layer[keep], -rank[keep], key_id[keep], is_code[keep]))]
    split = int(np.count_nonzero(~is_code[keep]))
    name_entries, code_entries = keep[:split], keep[split:]
    entries = {
        "layer": layer[keep].astype(np.uint8 if len(order) <= 256 else np.uint16),
        "row": row[keep].astype(np.int32),
        "kind": kind[keep].astype(np.uint8),
        "rank": rank[keep].astype(np.float32),
        "name_kind": name_kind[keep].astype(np.uint8),
    }
    per_layer = {}
    for i, name in enumerate(order):
        p = layers[name]
        mine = np.flatnonzero(entries["layer"] == i)
        best = np.full(p.count, -1, dtype=np.int32)
        # the row's most official entry: entries of a row sorted by name kind, first one wins
        by_kind = mine[np.lexsort((mine, entries["name_kind"][mine]))][::-1]
        best[entries["row"][by_kind]] = by_kind
        per_layer[("entry", name)] = best
        ids = [p.table[c] for c in p.arrays["id"]]
        per_layer[("ids", name)] = np.array(sorted(range(p.count), key=ids.__getitem__), dtype=np.int32)
        if p.kind == "polygon":
            hint = data.points.get(name)
            point, radius = _inside.points(p.geom, hint)
            per_layer[("inside", name)] = point
            per_layer[("radius", name)] = radius
    meta = {
        "format": nc.NAMES_FORMAT,
        "layers": order,
        "kinds": list(nc.PLACE_KINDS),
        "name_kinds": list(nc.NAME_KINDS),
        "entries": len(keep),
        "names": 0,
        "codes": 0,
    }
    names = _table(uniq[key_id[name_entries]], 0)
    codes = _table(uniq[key_id[code_entries]], split)
    meta["names"], meta["codes"] = len(names.offsets) - 1, len(codes.offsets) - 1
    return Plan(meta=meta, names=names, codes=codes, entries=entries, per_layer=per_layer)


def write(names_dir, plan, save, write_json):
    """Write `plan` into `names_dir` with the pack writer's own save and write_json."""
    names_dir.mkdir()
    write_json(names_dir / nc.NAMES_JSON, plan.meta)
    for prefix, table in (("name", plan.names), ("code", plan.codes)):
        (names_dir / f"{prefix}_keys.bin").write_bytes(table.blob)
        save(names_dir / f"{prefix}_keys.idx.npy", table.offsets)
        save(names_dir / f"{prefix}_start.npy", table.start)
    for stem, array in plan.entries.items():
        save(names_dir / f"{stem}.npy", array)
    for (sub, layer), array in plan.per_layer.items():
        (names_dir / sub).mkdir(exist_ok=True)
        save(names_dir / sub / f"{layer}.npy", array)


def _codes(values, table, what):
    lookup = {v: i for i, v in enumerate(table)}
    try:
        return np.fromiter((lookup[v] for v in values), dtype=np.int64, count=len(values))
    except KeyError as err:
        raise ValueError(f"names: {what} {err.args[0]!r} must be one of {', '.join(table)}") from None


def _table(sorted_keys, base):
    """Distinct keys of an already sorted key column, with each key's entry range."""
    if len(sorted_keys):
        first = np.ones(len(sorted_keys), dtype=bool)
        first[1:] = sorted_keys[1:] != sorted_keys[:-1]
        starts = np.flatnonzero(first)
    else:
        starts = np.zeros(0, dtype=np.int64)
    encoded = [k.encode("utf-8") for k in sorted_keys[starts]]
    offsets = np.zeros(len(encoded) + 1, dtype=np.int64)
    np.cumsum([len(b) for b in encoded], out=offsets[1:])
    if offsets[-1] >= 2**31:
        raise ValueError("names: the key table passes 2 GiB")
    start = np.append(starts, len(sorted_keys)) + base
    return _Table(blob=b"".join(encoded), offsets=offsets.astype(np.int32), start=start.astype(np.int32))
