"""Open packs (docs/pack-format.md) and answer questions from them.

Opening reads only the JSON manifests; every array is memory-mapped on first use, so a pack costs
next to nothing until it is queried, and then only for the layers and columns touched.

Polygon geometry is planar in (lat, lon), with the even-odd rule over all rings of a feature, as in
placewise.geo.shapes. A point exactly on an edge may be reported inside or outside, and the answer
may differ between neighbouring points on the same edge; don't rely on either.
"""

import hashlib
import json
import math
from pathlib import Path, PurePosixPath

import numpy as np

from placewise.constants import names as names_consts
from placewise.constants import packs as consts
from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo import haversine, lines
from placewise.model import BBox, Feature, Outline

from . import _geometry as gm
from ._boundary import Boundary
from ._edges import EdgeCaps
from ._lazy import once
from ._names import NameIndex
from ._points import PointIndex
from ._refine import Refinement

# queries x edges handled at once by nearest_edge_km, to bound memory
_EDGE_BLOCK = 1_000_000
_EDGE_SLACK_KM = 1e-9  # so rounding in the bound never drops the nearest edge
# nearest_edge_km measures every edge (cheaper to set up) for one feature up to these query x edges
_MEASURE_ALL_PAIRS = 65_536
# latitude bands (degrees) by which each feature's edges are listed for the exact even-odd test
_SLAB_DEG = consts.REFINE_CELL_DEG


class PackFormatError(ValueError):
    """Not a pack this code can read: missing or malformed manifest, unknown schema."""


class PackIntegrityError(ValueError):
    """A file is missing or doesn't match the checksum or size pack.json records for it."""


def open_pack(path, verify=False):
    """Open the pack directory at `path`. verify=True re-hashes every file first (slow for big
    packs; the store already verified them once after download)."""
    path = Path(path)
    manifest = _read_json(path / consts.PACK_JSON, consts.PACK_JSON)
    schema = manifest.get("schema")
    if schema != consts.SCHEMA:
        raise PackFormatError(
            f"{path}: pack schema {schema} is not supported; this placewise reads schema {consts.SCHEMA} "
            "(update placewise, or download a pack built for it)"
        )
    for key in ("name", "version", "layers", "files"):
        if key not in manifest:
            raise PackFormatError(f"{path / consts.PACK_JSON}: missing {key!r}")
    layers = {}
    for name in manifest["layers"]:
        meta = _read_json(path / name / consts.LAYER_JSON, f"{name}/{consts.LAYER_JSON}")
        cls = {"point": PointLayer, "polygon": PolygonLayer}.get(meta.get("kind"), Layer)
        layers[name] = cls(path / name, meta)
    pack = Pack(path, manifest, layers)
    if verify:
        pack.verify()
    return pack


class Pack:
    def __init__(self, path, manifest, layers):
        self.path = Path(path)
        self.manifest = manifest
        self.name = manifest["name"]
        self.version = manifest["version"]
        self.schema = manifest["schema"]
        self.created = manifest.get("created")
        self.sources = tuple(manifest.get("sources", ()))
        self.files = manifest["files"]
        self.layers = layers

    def __getitem__(self, name):
        try:
            return self.layers[name]
        except KeyError:
            raise KeyError(
                f"pack {self.name!r} has no layer {name!r}; it has {', '.join(self.layers)}"
            ) from None

    def __contains__(self, name):
        return name in self.layers

    @once
    def names(self):
        """The pack's name index (a NameIndex for forward search), or None when it has none."""
        if not (self.path / names_consts.NAMES_DIR / names_consts.NAMES_JSON).is_file():
            return None
        return NameIndex(self.path / names_consts.NAMES_DIR, self)

    def __iter__(self):
        return iter(self.layers.values())

    def __repr__(self):
        return f"<Pack {self.name}-{self.version}: {', '.join(self.layers)}>"

    def verify(self):
        """Re-hash every file pack.json lists; raise PackIntegrityError naming the first bad one."""
        root = self.path.resolve()
        for rel, meta in self.files.items():
            pure = PurePosixPath(rel)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise PackIntegrityError(f"{rel}: path escapes the pack")
            target = root.joinpath(*pure.parts)
            if not target.is_file():
                raise PackIntegrityError(f"{rel}: missing")
            size = target.stat().st_size
            if size != meta.get("size"):
                raise PackIntegrityError(f"{rel}: size {size}, expected {meta.get('size')}")
            digest = hashlib.sha256()
            with target.open("rb") as fh:
                while chunk := fh.read(consts.HASH_CHUNK):
                    digest.update(chunk)
            if digest.hexdigest() != meta.get("sha256"):
                raise PackIntegrityError(f"{rel}: sha256 mismatch (corrupt or modified)")


class Layer:
    """A layer's properties. Columns load lazily: numeric ones memory-mapped, string ones decoded
    once and cached."""

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

    def __len__(self):
        return self.count

    def __repr__(self):
        return f"<{type(self).__name__} {self.name}: {self.count} {self.kind}>"

    def column(self, field):
        """A field's values for every row: an ndarray for numeric fields (memory-mapped, read-only;
        nulls stay as stored: the sentinel, NaN), an object array of str for string fields."""
        kind = self._kind(field)
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


class PolygonLayer(Layer):
    @once
    def _grid_meta(self):
        return _read_json(
            self.path / consts.GRID_DIR / consts.GRID_META,
            f"{self.name}/{consts.GRID_DIR}/{consts.GRID_META}",
        )

    @property
    def cell_deg(self):
        return float(self._grid_meta["cell_deg"])

    @property
    def grid_shape(self):
        """(rows, cols) of the grid index."""
        return int(self._grid_meta["rows"]), int(self._grid_meta["cols"])

    @property
    def grid_inside(self):
        """Per cell, the feature that answers every point in it, or -1 (grid/inside.npy)."""
        return self._array(f"{consts.GRID_DIR}/inside.npy")

    @grid_inside.setter
    def grid_inside(self, value):
        # for tests and experiments: all -1 turns the shortcut off
        self._arrays[f"{consts.GRID_DIR}/inside.npy"] = value

    @once
    def _geom(self):
        lat = gm.from_e7(self._array(f"{consts.GEOM_DIR}/lat.npy"))
        lon = gm.from_e7(self._array(f"{consts.GEOM_DIR}/lon.npy"))
        ring = np.asarray(self._array(f"{consts.GEOM_DIR}/ring.npy"))
        part = np.asarray(self._array(f"{consts.GEOM_DIR}/part.npy"))
        feature = np.asarray(self._array(f"{consts.GEOM_DIR}/feature.npy"))
        nxt = gm.ring_next(ring, len(lat))
        return {
            "lat": lat,
            "lon": lon,
            "ring": ring,
            "part": part,
            "feature": feature,
            # a feature's rings are contiguous, so its edges are one slice of these arrays
            "vertex": ring[part[feature]],
            "lat_b": lat[nxt],
            "lon_b": lon[nxt],
        }

    @once
    def _bbox(self):
        return gm.from_e7(self._array(f"{consts.GEOM_DIR}/bbox.npy")).reshape(-1, 4)

    def query(self, lats, lons):
        """Index of the first feature containing each point, or -1. Vectorised; keeps the input's
        shape, plain int for a scalar. Cells the grid marks as wholly inside a feature answer
        without geometry; elsewhere only the cell's candidates get the exact test."""
        lat, lon = np.broadcast_arrays(np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64))
        shape = lat.shape
        flat_lat, flat_lon = gm.normalise(lat.ravel(), lon.ravel())
        result = np.full(flat_lat.shape, -1, dtype=np.int64)
        ok = np.flatnonzero(np.isfinite(flat_lat))
        if len(ok) and self.count:
            result[ok] = self._query(flat_lat[ok], flat_lon[ok])
        result = result.reshape(shape)
        return int(result) if result.ndim == 0 else result

    def _cell(self, lat, lon):
        rows, cols = self.grid_shape
        return gm.cell_rows(lat, self.cell_deg, rows) * cols + gm.cell_cols(lon, self.cell_deg, cols)

    def _query(self, lat, lon):
        cell = self._cell(lat, lon)
        result = np.asarray(self.grid_inside)[cell].astype(np.int64)
        offsets = self._array(f"{consts.GRID_DIR}/cell.npy")
        items = self._array(f"{consts.GRID_DIR}/items.npy")
        todo = np.flatnonzero(result < 0)
        ptr, stop = np.asarray(offsets[cell[todo]]), np.asarray(offsets[cell[todo] + 1])
        has = ptr < stop
        todo, ptr, stop = todo[has], ptr[has], stop[has]
        # round j tests each unresolved point against its cell's j-th candidate, so the first
        # feature containing a point is found without testing the ones after it
        while len(todo):
            feature = np.asarray(items[ptr]).astype(np.int64)
            hit = np.zeros(len(todo), dtype=bool)
            pts_lat, pts_lon = lat[todo], lon[todo]
            in_box = np.flatnonzero(self._in_bbox(feature, pts_lat, pts_lon))
            if len(in_box):
                hit[in_box] = self._contains(feature[in_box], pts_lat[in_box], pts_lon[in_box])
            result[todo[hit]] = feature[hit]
            ptr += 1
            more = ~hit & (ptr < stop)
            todo, ptr, stop = todo[more], ptr[more], stop[more]
        return result

    def _in_bbox(self, feature, lat, lon):
        south, west, north, east = self._bbox[feature].T
        in_lon = np.where(west <= east, (lon >= west) & (lon <= east), (lon >= west) | (lon <= east))
        return (lat >= south) & (lat <= north) & in_lon

    def _edges(self, i):
        g = self._geom
        vs, ve = g["vertex"][i], g["vertex"][i + 1]
        return g["lat"][vs:ve], g["lon"][vs:ve], g["lat_b"][vs:ve], g["lon_b"][vs:ve]

    def _contains(self, feature, lat, lon):
        """Even-odd containment of each point in its own feature, for all features at once:
        directly while a feature has been asked about few points, then through fine grids, built
        for it once it has been asked about enough to repay them."""
        self._tested += np.bincount(feature, minlength=self.count)
        refined = self._refined
        refined.add(feature[self._tested[feature] >= consts.REFINE_AFTER_POINTS])
        fine = refined.refined[feature]
        inside = np.empty(len(feature), dtype=bool)
        if fine.any():
            inside[fine] = refined.contains(lat[fine], lon[fine], feature[fine])
        if not fine.all():
            inside[~fine] = self._slabs.even_odd(lat[~fine], lon[~fine], feature[~fine])
        return inside

    @once
    def _slabs(self):
        g = self._geom
        return gm.Slabs(g["vertex"], (g["lat"], g["lon"], g["lat_b"], g["lon_b"]), _SLAB_DEG)

    @once
    def _refined(self):
        g = self._geom
        return Refinement(
            g["vertex"], (g["lat"], g["lon"], g["lat_b"], g["lon_b"]), self.cell_deg, self._slabs.even_odd
        )

    @once
    def _tested(self):
        return np.zeros(self.count, dtype=np.int64)

    def contains(self, lats, lons, features):
        """Whether each point lies inside the feature given for it (an index per point; -1 is in
        none), whichever feature `query` would name first. Vectorised, the same even-odd test as
        `query`; keeps the input's shape, plain bool for a scalar."""
        lat, lon, feature = np.broadcast_arrays(
            np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64), np.asarray(features)
        )
        shape = lat.shape
        flat_lat, flat_lon = gm.normalise(lat.ravel(), lon.ravel())
        feature = feature.ravel().astype(np.int64)
        if len(feature) and (feature.max() >= self.count or feature.min() < -1):
            raise IndexError(f"feature index out of range for a layer of {self.count}")
        inside = np.zeros(flat_lat.shape, dtype=bool)
        ok = np.flatnonzero((feature >= 0) & np.isfinite(flat_lat))
        ok = ok[self._in_bbox(feature[ok], flat_lat[ok], flat_lon[ok])]
        if len(ok):
            inside[ok] = self._contains(feature[ok], flat_lat[ok], flat_lon[ok])
        inside = inside.reshape(shape)
        return bool(inside) if inside.ndim == 0 else inside

    def query_all(self, lat, lon):
        """Indexes of every feature containing one point, ascending."""
        lat, lon = gm.normalise(np.array([float(lat)]), np.array([float(lon)]))
        if not (np.isfinite(lat[0]) and self.count):
            return []
        cell = int(self._cell(lat, lon)[0])
        offsets = self._array(f"{consts.GRID_DIR}/cell.npy")
        candidates = np.asarray(
            self._array(f"{consts.GRID_DIR}/items.npy")[offsets[cell] : offsets[cell + 1]]
        )
        found = []
        for f in candidates.astype(np.int64):
            if self._in_bbox(np.array([f]), lat, lon)[0] and gm.even_odd(lat, lon, *self._edges(int(f)))[0]:
                found.append(int(f))
        return found

    def query_every(self, lats, lons):
        """Every feature containing each point, for layers whose features overlap (regions): flat
        arrays (point, feature), sorted by point then feature; `point` indexes the flattened query.
        Vectorised query_all: each point is tested against all of its grid cell's candidates."""
        lat, lon = np.broadcast_arrays(np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64))
        flat_lat, flat_lon = gm.normalise(lat.ravel(), lon.ravel())
        ok = np.flatnonzero(np.isfinite(flat_lat))
        if not (len(ok) and self.count):
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        cell = self._cell(flat_lat[ok], flat_lon[ok])
        offsets = self._array(f"{consts.GRID_DIR}/cell.npy")
        start, stop = (
            np.asarray(offsets[cell]).astype(np.int64),
            np.asarray(offsets[cell + 1]).astype(np.int64),
        )
        if not (stop > start).any():  # no candidates: a layer far from every point
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        point = np.repeat(ok, stop - start)
        items = self._array(f"{consts.GRID_DIR}/items.npy")
        feature = np.asarray(items[_ranges(start, stop)]).astype(np.int64)
        in_box = self._in_bbox(feature, flat_lat[point], flat_lon[point])
        point, feature = point[in_box], feature[in_box]
        hit = (
            self._contains(feature, flat_lat[point], flat_lon[point])
            if len(point)
            else np.zeros(0, dtype=bool)
        )
        point, feature = point[hit], feature[hit]
        order = np.lexsort((feature, point))
        return point[order], feature[order]

    def bbox(self, i):
        """The feature's bounding box; west > east when it crosses the antimeridian."""
        return BBox(*self._bbox[self._row_index(i)].tolist())

    def bboxes(self):
        """Every feature's bounding box at once: a read-only (count, 4) array of (south, west,
        north, east) degrees, as bbox(i) gives one at a time."""
        boxes = self._bbox.view()
        boxes.flags.writeable = False
        return boxes

    def feature(self, i):
        """Feature i with its full geometry, its row as properties and its id."""
        i = self._row_index(i)
        g = self._geom
        outlines = []
        for p in range(g["feature"][i], g["feature"][i + 1]):
            rings = []
            for r in range(g["part"][p], g["part"][p + 1]):
                vs, ve = g["ring"][r], g["ring"][r + 1]
                rings.append(tuple(zip(g["lat"][vs:ve].tolist(), g["lon"][vs:ve].tolist(), strict=True)))
            outlines.append(Outline(tuple(rings)))
        properties = self.row(i)
        return Feature(outlines=tuple(outlines), properties=properties, id=properties.get("id"))

    def nearest_edge_km(self, lat, lon, i):
        """Distance (km) from each point to feature i's boundary, outer rings and holes, inside or
        out (i: one feature, or one per point). Exact on the sphere, treating each edge as a
        great-circle arc (the containment test treats edges as straight in lat/lon; the two differ
        by metres on long edges). Edges along ±180, where antimeridian features are cut, are not
        borders and are skipped. Keeps the broadcast shape; plain float for a scalar."""
        lat, lon, feature = np.broadcast_arrays(
            np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64), np.asarray(i)
        )
        shape = lat.shape
        flat_lat, flat_lon, feature = lat.ravel(), lon.ravel(), feature.ravel().astype(np.int64)
        if len(feature) and (feature.max() >= self.count or feature.min() < -self.count):
            bad = feature[(feature >= self.count) | (feature < -self.count)][0]
            raise IndexError(f"row {bad} out of range for layer {self.name!r} with {self.count} rows")
        feature = feature % max(self.count, 1)
        best = np.full(flat_lat.shape, np.inf)
        finite = np.isfinite(flat_lat) & np.isfinite(flat_lon)
        ok = np.flatnonzero(finite & (np.abs(flat_lat) <= 90))
        single = len(ok) and (feature[ok] == feature[ok[0]]).all()
        if single and len(ok) * self._edge_count(feature[ok[0]]) <= _MEASURE_ALL_PAIRS:
            best[ok] = self._every_edge_km(flat_lat[ok], flat_lon[ok], int(feature[ok[0]]))
        elif len(ok):
            best[ok] = self._edge_caps.km(flat_lat[ok], flat_lon[ok], feature[ok])
        odd = np.flatnonzero(finite & (np.abs(flat_lat) > 90))  # no such point; answered as before
        for f in np.unique(feature[odd]).tolist():
            at = odd[feature[odd] == f]
            best[at] = self._every_edge_km(flat_lat[at], flat_lon[at], f)
        best = best.reshape(shape)
        return float(best) if best.ndim == 0 else best

    @once
    def _edge_caps(self):
        g = self._geom

        def rings(f):
            return g["ring"][g["part"][g["feature"][f]] : g["part"][g["feature"][f + 1]] + 1]

        return EdgeCaps(g["lat"], g["lon"], g["lat_b"], g["lon_b"], rings, self.count)

    def _edge_count(self, i):
        g = self._geom
        return int(g["vertex"][i + 1] - g["vertex"][i])

    def _every_edge_km(self, flat_lat, flat_lon, i):
        """nearest_edge_km measuring every edge of the feature (pruned by the nearest vertex)."""
        ya, xa, yb, xb = self._edges(i)
        real = ~((np.abs(xa) == 180) & (np.abs(xb) == 180))
        ya, xa, yb, xb = ya[real], xa[real], yb[real], xb[real]
        best = np.full(flat_lat.shape, np.inf)
        if len(ya):
            a, b = lines._unit(ya, xa), lines._unit(yb, xb)
            length = haversine(ya, xa, yb, xb)
            step = max(1, _EDGE_BLOCK // len(ya))
            for q0 in range(0, len(flat_lat), step):
                qlat, qlon = flat_lat[q0 : q0 + step, None], flat_lon[q0 : q0 + step, None]
                to_start = haversine(qlat, qlon, ya[None, :], xa[None, :])
                # the nearest vertex bounds the answer; by the triangle inequality an edge can only
                # beat it if its start is within that distance plus the edge's own length
                bound = to_start.min(axis=1, keepdims=True)
                qi, ei = np.nonzero(to_start - length[None, :] <= bound + _EDGE_SLACK_KM)
                p = lines._unit(qlat[qi, 0], qlon[qi, 0])
                angle = lines._nearest_on_arcs(p, a[ei], b[ei])[1]
                chunk = np.full(len(qlat), np.inf)
                np.minimum.at(chunk, qi, angle * MEAN_RADIUS_KM)
                best[q0 : q0 + step] = chunk
        return best

    @once
    def _boundary(self):
        g = self._geom
        owner = np.repeat(np.arange(self.count), np.diff(g["vertex"]))
        return Boundary(g["lat"], g["lon"], g["lat_b"], g["lon_b"], owner)

    def near_boundary(self, lats, lons, radius_km):
        """Every feature whose boundary (outer rings and holes) comes within radius_km of each
        point, inside or out: flat arrays (point, feature, km), one row per pair at its nearest
        distance, sorted by point then feature; `point` indexes the flattened query. Distances
        as nearest_edge_km: exact, edges as great-circle arcs, cuts along ±180 not borders.
        Vectorised; meant for small radii (tens of km), where few edges are near."""
        lat, lon = np.broadcast_arrays(np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64))
        flat_lat, flat_lon = gm.normalise(lat.ravel(), lon.ravel())
        if not self.count:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64), np.zeros(0)
        return self._boundary.near(flat_lat, flat_lon, float(radius_km))

    def nearest_boundary(self, lats, lons, max_km=None):
        """(feature, km, lat, lon) per point: the feature whose boundary is nearest, how far, and
        the nearest point of that boundary; ties to the lower feature; -1, inf, NaN, NaN where no
        boundary is within max_km. Distances as nearest_edge_km. Keeps the input's shape; plain
        Python numbers for a scalar."""
        lat, lon = np.broadcast_arrays(np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64))
        shape = lat.shape
        flat_lat, flat_lon = gm.normalise(lat.ravel(), lon.ravel())
        if self.count:
            out = self._boundary.nearest(flat_lat, flat_lon, None if max_km is None else float(max_km))
        else:
            n = len(flat_lat)
            out = (np.full(n, -1, dtype=np.int64), np.full(n, np.inf), np.full(n, np.nan), np.full(n, np.nan))
        out = [a.reshape(shape) for a in out]
        if not shape:
            return int(out[0]), float(out[1]), float(out[2]), float(out[3])
        return tuple(out)


def _read_json(path, label):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PackFormatError(f"{path}: no {label}; is this a pack directory?") from None
    except (OSError, ValueError) as err:
        raise PackFormatError(f"{path}: unreadable {label}: {err}") from None
    if not isinstance(data, dict):
        raise PackFormatError(f"{path}: {label} must be a JSON object")
    return data


def _ranges(start, stop):
    """The ranges start[i]:stop[i], concatenated into one index array."""
    sizes = stop - start
    total = int(sizes.sum())
    if not total:
        return np.zeros(0, dtype=np.int64)
    shift = start - np.concatenate([[0], np.cumsum(sizes)[:-1]])
    return np.arange(total, dtype=np.int64) + np.repeat(shift, sizes)
