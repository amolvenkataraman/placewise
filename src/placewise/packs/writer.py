"""Write packs exactly as docs/pack-format.md describes, plus their release archives and index.

`write_pack` validates everything before touching the disk, writes into a temporary directory
beside the target and renames it into place, so a pack directory is either complete or absent.
"""

import datetime as dt
import hashlib
import io
import json
import lzma
import os
import re
import shutil
import tarfile
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from numbers import Integral, Real
from pathlib import Path

import numpy as np

from placewise.constants import licences
from placewise.constants import packs as consts
from placewise.model import Feature, PackInfo

from . import _geometry as gm


@dataclass
class LayerData:
    """One layer to write. Columns are lists (None for null) or numpy arrays, one row per feature;
    every layer needs "id" (unique, non-empty) and "name". Polygon features are in priority order:
    when several contain a point, the earliest wins."""

    name: str
    kind: str  # "point" | "polygon"
    columns: dict[str, Sequence]
    sources: tuple[str, ...]
    lat: np.ndarray | None = None  # point layers, degrees
    lon: np.ndarray | None = None
    features: Sequence[Feature] | None = None  # polygon layers, in priority order
    types: dict[str, str] = field(default_factory=dict)  # explicit field types; otherwise inferred
    nulls: dict[str, int] = field(default_factory=dict)  # integer null sentinels
    cell_deg: float = consts.DEFAULT_CELL_DEG  # grid cell for polygon layers


@dataclass
class _Prepared:
    """A validated layer, converted to what goes on disk."""

    name: str
    kind: str
    count: int
    sources: tuple[str, ...]
    fields: dict  # name -> {"type": ..., "null": ...}
    arrays: dict  # name -> ndarray (string fields as int32 codes into `table`)
    table: list  # the string table, "" first
    geom: dict  # file name -> ndarray
    cell_deg: float


def write_pack(out_dir, name, version, layers, created=None):
    """Write `<out_dir>/<name>-<version>/` and return its path. `created` is an ISO 8601 UTC
    timestamp (or datetime); it defaults to now, so pass it for reproducible output."""
    _check_name(name, "pack")
    if not isinstance(version, str) or not re.fullmatch(consts.VERSION_PATTERN, version):
        raise ValueError(f"pack version {version!r} must be CalVer YYYY.MM or YYYY.MM.N")
    layers = list(layers)
    if not layers:
        raise ValueError("a pack needs at least one layer")
    names = [layer.name for layer in layers]
    if dupes := sorted(n for n, k in Counter(names).items() if k > 1):
        raise ValueError(f"duplicate layer name(s): {', '.join(map(str, dupes))}")
    prepared = [_prepare(layer) for layer in layers]
    sources = list(dict.fromkeys(s for p in prepared for s in p.sources))

    out_dir = Path(out_dir)
    final = out_dir / f"{name}-{version}"
    if final.exists():
        raise FileExistsError(f"{final} already exists; packs are immutable, bump the version")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{final.name}.", suffix=".tmp", dir=out_dir))
    try:
        for p in prepared:
            _write_layer(tmp / p.name, p)
        manifest = {
            "schema": consts.SCHEMA,
            "name": name,
            "version": version,
            "created": _timestamp(created),
            "layers": names,
            "sources": sources,
            "files": {rel: _file_entry(tmp / rel) for rel in _relative_files(tmp)},
        }
        _write_json(tmp / consts.PACK_JSON, manifest)
        os.chmod(tmp, 0o755)  # mkdtemp makes it private; a pack is ordinary data
        os.rename(tmp, final)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


def archive(pack_dir):
    """Write `<name>-<version>.tar.xz` beside the pack directory and return its path. The bytes
    depend only on the pack's contents: entries sorted, times, owners and modes fixed."""
    pack_dir = Path(pack_dir)
    if not (pack_dir / consts.PACK_JSON).is_file():
        raise ValueError(f"{pack_dir} is not a pack (no {consts.PACK_JSON})")
    target = pack_dir.parent / f"{pack_dir.name}{consts.ARCHIVE_SUFFIX}"
    entries = [pack_dir, *sorted(pack_dir.rglob("*"), key=lambda p: p.relative_to(pack_dir).as_posix())]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in entries:
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError(f"{path}: packs hold only regular files and directories")
            info = tarfile.TarInfo((Path(pack_dir.name) / path.relative_to(pack_dir)).as_posix())
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
            if path.is_dir():
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            else:
                info.mode, info.size = 0o644, path.stat().st_size
                with path.open("rb") as fh:
                    tar.addfile(info, fh)
    # xz itself stores no timestamps, so the same tar gives the same archive
    _atomic_write_bytes(target, lzma.compress(buffer.getvalue(), format=lzma.FORMAT_XZ, preset=9))
    return target


def pack_info(archive_path):
    """The index entry for a release archive: name, version and sources from the pack.json inside
    it, sha256 and size from the archive's own bytes."""
    archive_path = Path(archive_path)
    with tarfile.open(archive_path, "r:xz") as tar:
        member = next(
            (
                m
                for m in tar.getmembers()
                if m.name.count("/") == 1 and m.name.endswith(f"/{consts.PACK_JSON}")
            ),
            None,
        )
        if member is None or not member.isfile():
            raise ValueError(f"{archive_path} has no <pack>/{consts.PACK_JSON}")
        manifest = json.loads(tar.extractfile(member).read())
    return PackInfo(
        name=manifest["name"],
        version=manifest["version"],
        schema=manifest["schema"],
        sha256=_sha256(archive_path),
        size_bytes=archive_path.stat().st_size,
        sources=tuple(manifest["sources"]),
    )


def write_index(out_dir, packs):
    """Write `<out_dir>/index.json` listing each PackInfo (one per pack name) and return its path."""
    packs = list(packs)
    if dupes := sorted(n for n, k in Counter(p.name for p in packs).items() if k > 1):
        raise ValueError(f"index lists pack(s) more than once: {', '.join(dupes)}")
    entries = {
        p.name: {
            "version": p.version,
            "schema": p.schema,
            "url": f"{p.name}-{p.version}{consts.ARCHIVE_SUFFIX}",
            "sha256": p.sha256,
            "size_bytes": p.size_bytes,
            "sources": list(p.sources),
        }
        for p in sorted(packs, key=lambda p: p.name)
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / consts.INDEX_JSON
    _atomic_write_bytes(target, _json_bytes({"schema": consts.SCHEMA, "packs": entries}))
    return target


# --- validation and conversion -----------------------------------------------------------------


def _prepare(layer):
    _check_name(layer.name, "layer")
    where = f"layer {layer.name!r}"
    if layer.kind not in consts.KINDS:
        raise ValueError(f"{where}: kind {layer.kind!r} must be one of {', '.join(consts.KINDS)}")
    sources = tuple(layer.sources or ())
    if not sources or not all(isinstance(s, str) and s for s in sources):
        raise ValueError(f"{where}: needs at least one source id for attribution")
    if denied := [s for s in sources if s in licences.DENIED_SOURCES]:
        raise ValueError(f"{where}: source(s) {', '.join(denied)} may not be redistributed")
    columns = dict(layer.columns)
    for required in consts.REQUIRED_FIELDS:
        if required not in columns:
            raise ValueError(f"{where}: every layer needs an {required!r} column")
    count = len(columns["id"])
    for f, values in columns.items():
        if not isinstance(f, str) or not re.fullmatch(consts.FIELD_PATTERN, f):
            raise ValueError(f"{where}: field name {f!r} must match {consts.FIELD_PATTERN}")
        if len(values) != count:
            raise ValueError(f"{where}: column {f!r} has {len(values)} rows, but 'id' has {count}")
    for f in set(layer.types) | set(layer.nulls):
        if f not in columns:
            raise ValueError(f"{where}: type or null given for missing column {f!r}")

    fields, arrays, table = {}, {}, {"": 0}
    for f, values in columns.items():
        kind, array = _column(where, f, values, layer.types.get(f), layer.nulls.get(f))
        if f in consts.REQUIRED_FIELDS and kind != "str":
            raise ValueError(f"{where}: {f!r} must be a string column")
        if f == "id":
            if "" in array:
                raise ValueError(f"{where}: every id must be a non-empty string")
            if dupes := sorted(s for s, k in Counter(array).items() if k > 1):
                raise ValueError(f"{where}: ids must be unique; repeated: {', '.join(dupes[:5])}")
        fields[f] = {"type": kind}
        if f in layer.nulls:
            fields[f]["null"] = int(layer.nulls[f])
        if kind == "str":
            array = np.fromiter((table.setdefault(s, len(table)) for s in array), dtype=np.int32, count=count)
        arrays[f] = array

    if layer.kind == "point":
        geom = _point_geometry(where, layer, count)
    else:
        if not (isinstance(layer.cell_deg, Real) and 0 < layer.cell_deg <= 90):
            raise ValueError(f"{where}: cell_deg must be in (0, 90], not {layer.cell_deg!r}")
        geom = _polygon_geometry(where, layer, count)
    return _Prepared(
        name=layer.name,
        kind=layer.kind,
        count=count,
        sources=sources,
        fields=fields,
        arrays=arrays,
        table=list(table),
        geom=geom,
        cell_deg=float(layer.cell_deg),
    )


def _column(where, name, values, kind, null):
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
        if not all(v is None or isinstance(v, str) for v in items):
            raise ValueError(f"{label}: a str field holds only strings (or None)")
        return kind, ["" if v is None else v for v in items]
    dtype = _dtype(kind)
    if kind == "bool":
        if not all(isinstance(v, bool | np.bool_) for v in items):
            raise ValueError(f"{label}: a bool field holds only True / False")
        return kind, np.asarray(items, dtype=dtype)
    if kind in consts.INT_TYPES:
        info = np.iinfo(dtype)
        if null is not None and not (isinstance(null, Integral) and info.min <= null <= info.max):
            raise ValueError(f"{label}: null sentinel {null!r} doesn't fit {kind}")
        if null is None and any(v is None for v in items):
            raise ValueError(f"{label}: has None but no null sentinel in `nulls`")
        items = [null if v is None else v for v in items]
        if not all(isinstance(v, Integral) and not isinstance(v, bool | np.bool_) for v in items):
            raise ValueError(f"{label}: an integer field holds only integers")
        if items and not (info.min <= min(items) and max(items) <= info.max):
            raise ValueError(f"{label}: values outside the {kind} range {info.min}..{info.max}")
        return kind, np.asarray(items, dtype=dtype)
    items = [np.nan if v is None else v for v in items]
    if not all(isinstance(v, Real) and not isinstance(v, bool | np.bool_) for v in items):
        raise ValueError(f"{label}: a float field holds only numbers (or None / NaN)")
    return kind, np.asarray(items, dtype=dtype)


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


def _check_name(name, what):
    if not isinstance(name, str) or not re.fullmatch(consts.NAME_PATTERN, name):
        raise ValueError(
            f"{what} name {name!r} must match {consts.NAME_PATTERN} (it becomes a directory name)"
        )


def _point_geometry(where, layer, count):
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


def _polygon_geometry(where, layer, count):
    features = list(layer.features) if layer.features is not None else None
    if features is None or len(features) != count:
        got = "none" if features is None else len(features)
        raise ValueError(f"{where}: a polygon layer needs one entry in features per row ({count}), got {got}")
    lats, lons, ring_off, part_off, feat_off, bbox = [], [], [0], [0], [0], []
    vertices = 0
    for i, feature in enumerate(features):
        if not isinstance(feature, Feature):
            raise ValueError(f"{where}: features[{i}] is a {type(feature).__name__}, not a Feature")
        spans, south, north = [], [], []
        for outline in feature.outlines:
            for ring in outline.rings:
                pts = np.asarray(ring, dtype=np.float64)
                if len(pts) > 1 and np.array_equal(pts[0], pts[-1]):
                    pts = pts[:-1]  # rings are stored open; the closing edge is implicit
                lat, lon = gm.to_e7(pts[:, 0]), gm.to_e7(pts[:, 1])
                lats.append(lat)
                lons.append(lon)
                vertices += len(pts)
                ring_off.append(vertices)
                spans.append((lon.min(), lon.max()))
                south.append(lat.min())
                north.append(lat.max())
            part_off.append(len(ring_off) - 1)
        feat_off.append(len(part_off) - 1)
        west, east = gm.circular_lon_range(spans)
        bbox.append((min(south), west, max(north), east))
    ring_off = np.asarray(ring_off, dtype=np.int64)
    part_off = np.asarray(part_off, dtype=np.int64)
    feat_off = np.asarray(feat_off, dtype=np.int64)
    lat = np.concatenate(lats) if lats else np.zeros(0, dtype=np.int32)
    lon = np.concatenate(lons) if lons else np.zeros(0, dtype=np.int32)
    _check_antimeridian(where, lat, lon, ring_off, part_off, feat_off)
    return {
        "lat.npy": lat,
        "lon.npy": lon,
        "ring.npy": ring_off,
        "part.npy": part_off,
        "feature.npy": feat_off,
        "bbox.npy": np.asarray(bbox, dtype=np.int32).reshape(-1, 4),
    }


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


# --- files -------------------------------------------------------------------------------------


def _write_layer(layer_dir, p):
    (layer_dir / consts.COL_DIR).mkdir(parents=True)
    _write_json(
        layer_dir / consts.LAYER_JSON,
        {
            "name": p.name,
            "kind": p.kind,
            "count": p.count,
            "sources": list(p.sources),
            "fields": p.fields,
            "coords": consts.COORDS,
        },
    )
    encoded = [s.encode("utf-8") for s in p.table]
    offsets = np.zeros(len(encoded) + 1, dtype=np.int64)
    np.cumsum([len(b) for b in encoded], out=offsets[1:])
    (layer_dir / consts.STRINGS_BIN).write_bytes(b"".join(encoded))
    _save(layer_dir / consts.STRINGS_IDX, offsets)
    for f, array in p.arrays.items():
        _save(layer_dir / consts.COL_DIR / f"{f}.npy", array)
    (layer_dir / consts.GEOM_DIR).mkdir()
    for file_name, array in p.geom.items():
        _save(layer_dir / consts.GEOM_DIR / file_name, array)
    if p.kind == "polygon":
        _write_grid(layer_dir / consts.GRID_DIR, p.geom, p.cell_deg)


def _write_grid(grid_dir, geom, cell_deg):
    """Candidates per cell and the cells one feature answers outright.

    A feature is a candidate in a cell when it may contain some point of it: an edge touches the
    cell, or it covers the cell wholly (a feature whose bbox touches a cell but whose shape misses
    it is left out). A cell is marked `inside` f when f covers it wholly (corners inside and no edge
    touching it, so a cell in a hole is not) and every earlier candidate misses it entirely, so f is
    the first-match answer for every point in it."""
    rows, cols = gm.grid_shape(cell_deg)
    lat, lon = gm.from_e7(geom["lat.npy"]), gm.from_e7(geom["lon.npy"])
    ring_off, part_off, feat_off = geom["ring.npy"], geom["part.npy"], geom["feature.npy"]
    nxt = gm.ring_next(ring_off, len(lat))
    bbox = gm.from_e7(geom["bbox.npy"])
    cells, feats, status = [], [], []  # status 1: wholly inside, 2: an edge touches the cell
    for f in range(len(feat_off) - 1):
        vs, ve = ring_off[part_off[feat_off[f]]], ring_off[part_off[feat_off[f + 1]]]
        ya, xa, yb, xb = lat[vs:ve], lon[vs:ve], lat[nxt[vs:ve]], lon[nxt[vs:ve]]
        candidates = gm.bbox_cells(*bbox[f], cell_deg, rows, cols)
        on_edge = np.isin(candidates, gm.edge_cells(ya, xa, yb, xb, cell_deg, rows, cols))
        free = candidates[~on_edge]
        # no edge touches a free cell, so its centre speaks for all of it
        centre_lat = -90.0 + (free // cols + 0.5) * cell_deg
        centre_lon = -180.0 + (free % cols + 0.5) * cell_deg
        covered = free[gm.even_odd_rows(centre_lat, centre_lon, ya, xa, yb, xb)]
        cells += [candidates[on_edge], covered]
        feats.append(np.full(on_edge.sum() + len(covered), f, dtype=np.int64))
        status += [np.full(on_edge.sum(), 2, dtype=np.int8), np.ones(len(covered), dtype=np.int8)]
    cell = np.concatenate([np.zeros(0, dtype=np.int64), *cells])
    feat = np.concatenate([np.zeros(0, dtype=np.int64), *feats])
    stat = np.concatenate([np.zeros(0, dtype=np.int8), *status])
    order = np.lexsort((feat, cell))
    cell, feat, stat = cell[order], feat[order], stat[order]
    offsets = np.zeros(rows * cols + 1, dtype=np.int64)
    np.cumsum(np.bincount(cell, minlength=rows * cols), out=offsets[1:])
    inside = np.full(rows * cols, -1, dtype=np.int32)
    first_cells, first = np.unique(cell, return_index=True)
    inside[first_cells] = np.where(stat[first] == 1, feat[first], -1)

    grid_dir.mkdir()
    _write_json(grid_dir / consts.GRID_META, {"cell_deg": cell_deg, "rows": rows, "cols": cols})
    _save(grid_dir / "cell.npy", offsets)
    _save(grid_dir / "items.npy", feat.astype(np.int32))
    _save(grid_dir / "inside.npy", inside)


def _save(path, array):
    array = np.ascontiguousarray(array)
    if array.dtype.byteorder == ">":
        array = array.astype(array.dtype.newbyteorder("<"))
    np.save(path, array, allow_pickle=False)


def _json_bytes(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path, obj):
    path.write_bytes(_json_bytes(obj))


def _atomic_write_bytes(target, data):
    fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _relative_files(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def _file_entry(path):
    return {"sha256": _sha256(path), "size": path.stat().st_size}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(consts.HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(created):
    if created is None:
        created = dt.datetime.now(dt.timezone.utc)
    if isinstance(created, dt.datetime):
        if created.tzinfo is not None:
            created = created.astimezone(dt.timezone.utc)
        return created.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(created)
