"""Shapefile records and dBASE columns as numpy arrays, for inputs `placewise.io.read_shapefile`
doesn't take: line files (river centerlines), files too big to hold as Python tuples
(HydroLAKES), and the first records of a file cut short at a record boundary.

Geometry comes back as (lon, lat) float64 arrays, one per part, in the file's order (outer rings
clockwise, holes counter-clockwise for polygons); nothing is converted or checked beyond the shape
type. Text is decoded and stripped of the spaces and NUL bytes writers pad with.
"""

import struct
from pathlib import Path

import numpy as np

_LINE_TYPES = {3, 13, 23}  # PolyLine, PolyLineZ, PolyLineM (Z and M values are ignored)
_POLYGON_TYPES = {5, 15, 25}
_NULL_SHAPE = 0
_HEADER = 100


def read_shapes(path, limit=None):
    """Yield each record's parts ([(n, 2) lon/lat arrays]) or None for a null shape: the first
    `limit` records, or every complete record (a file cut short ends at its last whole one)."""
    data = Path(path).read_bytes()
    if len(data) < _HEADER or struct.unpack(">i", data[:4])[0] != 9994:
        raise ValueError(f"{Path(path).name} is not a shapefile")
    offset, count = _HEADER, 0
    while offset + 8 <= len(data) and (limit is None or count < limit):
        words = struct.unpack(">i", data[offset + 4 : offset + 8])[0]
        start, offset = offset + 8, offset + 8 + 2 * words
        if offset > len(data):
            return  # an incomplete last record
        count += 1
        shape_type = struct.unpack("<i", data[start : start + 4])[0]
        if shape_type == _NULL_SHAPE:
            yield None
            continue
        if shape_type not in _LINE_TYPES | _POLYGON_TYPES:
            raise ValueError(f"{Path(path).name}: shape type {shape_type} is not a line or polygon")
        n_parts, n_points = struct.unpack("<2i", data[start + 36 : start + 44])
        parts = np.frombuffer(data, "<i4", n_parts, start + 44)
        points = np.frombuffer(data, "<f8", 2 * n_points, start + 44 + 4 * n_parts).reshape(-1, 2)
        yield [p.copy() for p in np.split(points, parts[1:])]


def record_ends(shx_path):
    """Byte offset in the .shp just past each record, from the index file (.shx)."""
    data = Path(shx_path).read_bytes()
    rows = np.frombuffer(data, ">i4", offset=_HEADER).reshape(-1, 2).astype(np.int64)
    return rows[:, 0] * 2 + 8 + rows[:, 1] * 2


def read_dbf(path, encoding="utf-8", limit=None, fields=None):
    """{field: [text, ...]}: every column (or just `fields`) as stripped strings, "" for blanks,
    for the first `limit` records (all by default). Numbers stay text: see `numbers`."""
    data = Path(path).read_bytes()
    n_records, header_len, record_len = struct.unpack("<IHH", data[4:12])
    layout, pos, cursor = [], 32, 1  # byte 0 of each record is the deletion flag
    while data[pos] != 0x0D:
        name = data[pos : pos + 11].split(b"\x00")[0].decode("ascii")
        length = data[pos + 16]
        layout.append((name, cursor, length))
        cursor += length
        pos += 32
    n = n_records if limit is None else min(limit, n_records)
    n = min(n, (len(data) - header_len) // record_len)
    table = np.frombuffer(data, np.uint8, n * record_len, header_len).reshape(n, record_len)
    wanted = set(fields) if fields is not None else None
    columns = {}
    for name, start, length in layout:
        if wanted is not None and name not in wanted:
            continue
        raw = np.ascontiguousarray(table[:, start : start + length]).view(f"S{length}").ravel()
        columns[name] = [v.decode(encoding, errors="replace").strip(" \t\r\n\x00") for v in raw.tolist()]
    return columns


def numbers(values):
    """float64 array from dBASE number text; NaN for blanks and the "****" of overflowed fields."""
    out = np.full(len(values), np.nan)
    for i, v in enumerate(values):
        try:
            out[i] = float(v)
        except ValueError:
            continue
    return out
