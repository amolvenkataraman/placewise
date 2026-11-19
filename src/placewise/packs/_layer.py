"""A pack's layers as open_pack (reader.py) gives them: `Layer`, the properties of any layer, and
`PointLayer`, a point layer's coordinates and nearest-neighbour search (PolygonLayer is in
_polygon_layer.py). Every array is memory-mapped on first use, so a layer costs next to nothing
until it is queried, and then only for the columns touched. Also the JSON manifests' reader.
"""

import json
import math
from pathlib import Path

import numpy as np

from placewise.constants import packs as consts

from ._distances.points import PointIndex
from ._geometry import planar as gm
from ._ids import DerivedIds
from ._lazy import once


class PackFormatError(ValueError):
    """Not a pack this code can read: missing or malformed manifest, unknown schema."""


class Layer:
    """A layer's properties. Columns load lazily: numeric ones memory-mapped, string ones decoded
    once and cached. Ids a layer derives from a template (docs/pack-format.md, "Derived ids") read
    exactly as stored ones."""

    def __init__(self, path, meta):
        self.path = Path(path)
        self.meta = meta
        self.name = meta["name"]
        self.kind = meta["kind"]
        self.count = int(meta["count"])
        self.sources = tuple(meta.get("sources", ()))
        self.fields = {f: spec["type"] for f, spec in meta["fields"].items()}
        self.nulls = {f: spec["null"] for f, spec in meta["fields"].items() if "null" in spec}
        self._arrays = {}
        self._decoded = {}
        id_spec = meta["fields"].get("id", {})
        self._ids = DerivedIds(self, id_spec) if "template" in id_spec else None

    def __len__(self):
        return self.count

    def __repr__(self):
        return f"<{type(self).__name__} {self.name}: {self.count} {self.kind}>"

    def column(self, field):
        """A field's values for every row: an ndarray for numeric fields (memory-mapped, read-only;
        nulls stay as stored: the sentinel, NaN), an object array of str for string fields."""
        kind = self._kind(field)
        if self._derived(field):
            if field not in self._decoded:
                self._decoded[field] = np.array(self._ids.column(), dtype=object)
                self._decoded[field].flags.writeable = False
            return self._decoded[field]
        codes = self._array(f"{consts.COL_DIR}/{field}.npy")
        if kind != "str":
            return codes
        if field not in self._decoded:
            # decode each distinct string once, however many rows share it
            unique, inverse = np.unique(np.asarray(codes), return_inverse=True)
            decoded = self._strings_of(unique)[inverse.ravel()]
            decoded.flags.writeable = False  # it's cached: one caller mustn't change another's
            self._decoded[field] = decoded
        return self._decoded[field]

    def distinct(self, field):
        """(values, inverse) of a string field, as np.unique(column(field), return_inverse=True)
        gives them (values sorted, an object array; column(field) == values[inverse]), but found
        from the stored string ids, without sorting every row's string."""
        if self._kind(field) != "str":
            raise TypeError(f"field {field!r} of layer {self.name!r} is not a string field")
        if self._derived(field):
            values, inverse = np.unique(self.column(field), return_inverse=True)
            return values, inverse.ravel()
        codes = np.asarray(self._array(f"{consts.COL_DIR}/{field}.npy"))
        unique, inverse = np.unique(codes, return_inverse=True)  # one id per distinct string
        strings = self._strings_of(unique)
        order = np.array(sorted(range(len(strings)), key=strings.__getitem__), dtype=np.int64)
        rank = np.empty(len(order), dtype=np.int64)
        rank[order] = np.arange(len(order))
        return strings[order], rank[inverse.ravel()]

    def value(self, field, i):
        """One value as a plain Python object; nulls (sentinel, NaN, empty string) become None."""
        kind = self._kind(field)
        if self._derived(field):
            return self._ids.value(self._row_index(i))
        raw = self._array(f"{consts.COL_DIR}/{field}.npy")[self._row_index(i)]
        if kind == "str":
            return self._string(int(raw)) if raw else None
        if kind == "bool":
            return bool(raw)
        if kind in consts.INT_TYPES:
            v = int(raw)
            return None if v == self.nulls.get(field) else v
        v = float(raw)
        return None if math.isnan(v) else v

    def row(self, i):
        """Every field of row i, nulls as None."""
        return {f: self.value(f, i) for f in self.fields}

    def find(self, field, value):
        """Rows (ascending int array) whose field equals value exactly: ids, codes and the like."""
        kind = self._kind(field)
        if self._derived(field):
            return np.flatnonzero(self.column(field) == value).astype(np.int64)
        codes = np.asarray(self._array(f"{consts.COL_DIR}/{field}.npy"))
        if kind == "str":
            value = self._string_ids.get(value)
            if value is None:
                return np.zeros(0, dtype=np.int64)
        return np.flatnonzero(codes == value).astype(np.int64)

    def _kind(self, field):
        try:
            return self.fields[field]
        except KeyError:
            raise KeyError(f"layer {self.name!r} has no field {field!r}") from None

    def _derived(self, field):
        return field == "id" and self._ids is not None

    def _row_index(self, i):
        i = int(i)
        if not -self.count <= i < self.count:
            raise IndexError(f"row {i} out of range for layer {self.name!r} with {self.count} rows")
        return i % self.count

    def _array(self, rel):
        if rel not in self._arrays:
            self._arrays[rel] = np.load(self.path / rel, mmap_mode="r", allow_pickle=False)
        return self._arrays[rel]

    @once
    def _strings(self):
        return (self.path / consts.STRINGS_BIN).read_bytes(), np.asarray(self._array(consts.STRINGS_IDX))

    def _string(self, k):
        blob, idx = self._strings
        return blob[idx[k] : idx[k + 1]].decode("utf-8")

    def _strings_of(self, ids):
        """The strings with ids `ids`, as an object array."""
        blob, idx = self._strings
        ids = np.asarray(ids, dtype=np.int64)
        out = np.empty(len(ids), dtype=object)
        starts, stops = idx[ids].tolist(), idx[ids + 1].tolist()
        out[:] = [blob[a:b].decode("utf-8") for a, b in zip(starts, stops, strict=True)]
        return out

    @once
    def _string_ids(self):
        return {self._string(k): k for k in range(len(self._strings[1]) - 1)}


class PointLayer(Layer):
    @once
    def lat(self):
        """Latitudes in degrees (float64)."""
        return gm.from_e7(self._array(f"{consts.GEOM_DIR}/lat.npy"))

    @once
    def lon(self):
        """Longitudes in degrees (float64)."""
        return gm.from_e7(self._array(f"{consts.GEOM_DIR}/lon.npy"))

    @once
    def index(self):
        """The layer's points as a PointIndex (built on first use; indexes are row numbers)."""
        return PointIndex(self.lat, self.lon)

    def nearest(self, lat, lon, k=1, max_km=None):
        """(indexes, distances_km) of the k nearest points to each query point (haversine), nearest
        first, ties to the lower index; -1 and inf where there are fewer than k (within max_km).
        Shapes: the query's, plus a trailing k axis when k > 1; plain int and float for a scalar
        query with k=1. See PointIndex.nearest."""
        return self.index.nearest(lat, lon, k=k, max_km=max_km)

    def within(self, lat, lon, radius_km):
        """(indexes, distances_km) of every point within radius_km of one point, nearest first."""
        return self.index.within(lat, lon, radius_km)


def read_json(path, label):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackFormatError(f"{path}: no {label}; is this a pack directory?") from None
    except (OSError, ValueError) as err:
        raise PackFormatError(f"{path}: unreadable {label}: {err}") from None
    if not isinstance(data, dict):
        raise PackFormatError(f"{path}: {label} must be a JSON object")
    return data
