"""LayerData contents as the arrays a pack stores (docs/pack-format.md): typed columns, and point
and polygon geometry as flat e7 arrays with their offsets and bboxes. Every check raises
ValueError naming the layer and column or feature at fault."""

import itertools
from numbers import Integral, Real

import numpy as np

from placewise.constants import packs as consts
from placewise.model import Feature

from . import _geometry as gm


def column(where, name, values, kind, null):
    """(type, values): a list of str for str fields, else an ndarray of the field's dtype."""
    label = f"{where}: column {name!r}"
    if kind is None:
        kind = _infer_type(label, values)
    if kind not in consts.FIELD_TYPES:
        raise ValueError(f"{label}: type {kind!r} is not one of {', '.join(consts.FIELD_TYPES)}")
    if null is not None and kind not in consts.INT_TYPES:
        raise ValueError(f"{label}: only integer fields take a null sentinel (str nulls are '', floats NaN)")
    items = values.tolist() if isinstance(values, np.ndarray) else list(values)
    if kind == "str":
        if not _only(items, str, type(None)) and not all(v is None or isinstance(v, str) for v in items):
            raise ValueError(f"{label}: a str field holds only strings (or None)")
        return kind, ["" if v is None else v for v in items]
    dtype = _dtype(kind)
    if kind == "bool":
        if not _only(items, bool) and not all(isinstance(v, bool | np.bool_) for v in items):
            raise ValueError(f"{label}: a bool field holds only True / False")
        return kind, np.asarray(items, dtype=dtype)
    if kind in consts.INT_TYPES:
        info = np.iinfo(dtype)
        if null is not None and not (isinstance(null, Integral) and info.min <= null <= info.max):
            raise ValueError(f"{label}: null sentinel {null!r} doesn't fit {kind}")
        if null is None and any(v is None for v in items):
            raise ValueError(f"{label}: has None but no null sentinel in `nulls`")
        items = [null if v is None else v for v in items]
        if not _only(items, int) and not all(
            isinstance(v, Integral) and not isinstance(v, bool | np.bool_) for v in items
        ):
            raise ValueError(f"{label}: an integer field holds only integers")
        if items and not (info.min <= min(items) and max(items) <= info.max):
            raise ValueError(f"{label}: values outside the {kind} range {info.min}..{info.max}")
        return kind, np.asarray(items, dtype=dtype)
    items = [np.nan if v is None else v for v in items]
    if not _only(items, float, int) and not all(
        isinstance(v, Real) and not isinstance(v, bool | np.bool_) for v in items
    ):
        raise ValueError(f"{label}: a float field holds only numbers (or None / NaN)")
    return kind, np.asarray(items, dtype=dtype)


def _only(items, *types):
    """Whether every item's type is exactly one of `types`: the common case, checked at C speed
    before the general (subclass-aware, slower) test."""
    return set(map(type, items)) <= set(types)


def _infer_type(label, values):
    if isinstance(values, np.ndarray):
        if values.dtype.kind == "b":
            return "bool"
        if values.dtype.kind in "iuf":
            kind = f"{values.dtype.kind}{values.dtype.itemsize}"
            if kind not in consts.FIELD_TYPES:
                raise ValueError(
                    f"{label}: dtype {values.dtype} has no pack type ({', '.join(consts.FIELD_TYPES)})"
                )
            return kind
        if values.dtype.kind not in "UO":
            raise ValueError(f"{label}: can't store dtype {values.dtype}")
        values = values.tolist()
    present = [v for v in values if v is not None]
    if all(isinstance(v, str) for v in present):
        return "str"  # including an empty or all-None column
    if all(isinstance(v, bool | np.bool_) for v in present):
        return "bool"
    if all(isinstance(v, Integral) and not isinstance(v, bool | np.bool_) for v in present):
        return "i8"
    if all(isinstance(v, Real) and not isinstance(v, bool | np.bool_) for v in present):
        return "f8"
    raise ValueError(f"{label}: mixed or unsupported values; give its type in `types`")


def _dtype(kind):
    return np.dtype(bool) if kind == "bool" else np.dtype(kind).newbyteorder("<")


def point_geometry(where, layer, count):
    if layer.lat is None or layer.lon is None:
        raise ValueError(f"{where}: a point layer needs lat and lon arrays")
    lat, lon = np.asarray(layer.lat, dtype=np.float64), np.asarray(layer.lon, dtype=np.float64)
    if lat.shape != (count,) or lon.shape != (count,):
        raise ValueError(f"{where}: lat and lon need shape ({count},), got {lat.shape} and {lon.shape}")
    if not (np.all(np.isfinite(lat)) and np.all(np.abs(lat) <= 90)):
        raise ValueError(f"{where}: every lat must be finite and within ±90")
    if not (np.all(np.isfinite(lon)) and np.all(np.abs(lon) <= 180)):
        raise ValueError(f"{where}: every lon must be finite and within ±180")
    return {"lat.npy": gm.to_e7(lat), "lon.npy": gm.to_e7(lon)}


def polygon_geometry(where, layer, count):
    features = list(layer.features) if layer.features is not None else None
    if features is None or len(features) != count:
        got = "none" if features is None else len(features)
        raise ValueError(f"{where}: a polygon layer needs one entry in features per row ({count}), got {got}")
    rings, part_off, feat_off = [], [0], [0]
    for i, feature in enumerate(features):
        if not isinstance(feature, Feature):
            raise ValueError(f"{where}: features[{i}] is a {type(feature).__name__}, not a Feature")
        for outline in feature.outlines:
            rings.extend(outline.rings)
            part_off.append(len(rings))
        feat_off.append(len(part_off) - 1)
    part_off = np.asarray(part_off, dtype=np.int64)
    feat_off = np.asarray(feat_off, dtype=np.int64)
    lat, lon, ring_off = _flat_rings(rings)
    bbox = np.zeros((count, 4), dtype=np.int32)
    if count:
        # every feature has a ring and every ring a vertex (Outline checks), so no slice is empty
        starts, feature_rings = ring_off[:-1], part_off[feat_off]
        ring_south, ring_north = np.minimum.reduceat(lat, starts), np.maximum.reduceat(lat, starts)
        ring_west, ring_east = np.minimum.reduceat(lon, starts), np.maximum.reduceat(lon, starts)
        bbox[:, 0] = np.minimum.reduceat(ring_south, feature_rings[:-1])
        bbox[:, 2] = np.maximum.reduceat(ring_north, feature_rings[:-1])
        bbox[:, 1], bbox[:, 3] = ring_west[feature_rings[:-1]], ring_east[feature_rings[:-1]]
        for f in np.flatnonzero(np.diff(feature_rings) > 1):
            r0, r1 = feature_rings[f], feature_rings[f + 1]
            bbox[f, 1], bbox[f, 3] = gm.circular_lon_range(
                zip(ring_west[r0:r1], ring_east[r0:r1], strict=True)
            )
    _check_antimeridian(where, lat, lon, ring_off, part_off, feat_off)
    return {
        "lat.npy": lat,
        "lon.npy": lon,
        "ring.npy": ring_off,
        "part.npy": part_off,
        "feature.npy": feat_off,
        "bbox.npy": bbox,
    }


def _flat_rings(rings):
    """(lat, lon, ring offsets): every ring's vertices in e7, stored open (a closing vertex that
    repeats the first is dropped; the closing edge is implicit)."""
    sizes = np.fromiter(map(len, rings), dtype=np.int64, count=len(rings))
    flat = np.fromiter(
        itertools.chain.from_iterable(itertools.chain.from_iterable(rings)),
        dtype=np.float64,
        count=2 * int(sizes.sum()),
    ).reshape(-1, 2)
    ends = np.cumsum(sizes)
    starts = ends - sizes
    closed = (sizes > 1) & np.all(flat[starts] == flat[ends - 1], axis=1)
    keep = np.ones(len(flat), dtype=bool)
    keep[ends[closed] - 1] = False
    ring_off = np.zeros(len(rings) + 1, dtype=np.int64)
    np.cumsum(sizes - closed, out=ring_off[1:])
    return gm.to_e7(flat[keep, 0]), gm.to_e7(flat[keep, 1]), ring_off


def _check_antimeridian(where, lat, lon, ring_off, part_off, feat_off):
    """Refuse edges that jump more than 180° of longitude: in planar geometry they would sweep
    round the world the wrong way. An edge from +180 to -180 along a parallel is fine: it is how
    a ring spanning every longitude (Antarctica) closes."""
    if not len(lon):
        return
    nxt = gm.ring_next(ring_off, len(lon))
    a, b = lon.astype(np.int64), lon[nxt].astype(np.int64)
    limit = 180 * consts.E7
    along_parallel = (np.abs(a) == limit) & (np.abs(b) == limit) & (lat == lat[nxt])
    bad = (np.abs(b - a) > limit) & ~along_parallel
    if bad.any():
        ring = np.searchsorted(ring_off, np.flatnonzero(bad)[0], "right") - 1
        feature = np.searchsorted(feat_off, np.searchsorted(part_off, ring, "right") - 1, "right") - 1
        raise ValueError(
            f"{where}: feature {feature} has an edge crossing the antimeridian; "
            "split it at ±180 into separate polygons (RFC 7946 §3.1.9)"
        )
