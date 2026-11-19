"""Read polygon features from a GeoPackage (OGC 12-128r19) with the standard library's sqlite3.

A GeoPackage is an SQLite file: `gpkg_contents` lists its feature tables, `gpkg_geometry_columns`
names each table's geometry column and spatial reference, and every geometry is a small header
(magic "GP", version, flags, srs_id, optional envelope; spec 2.1.3) followed by Well-Known Binary
(OGC 06-103r4 / ISO 19125). Only (Multi)Polygons are read, in any byte order, with Z and M
ordinates dropped; anything else is a ValueError naming the WKB type, so a schema change is loud.

Rows are streamed, so a multi-GB file never sits in memory: only the current row's rings do.
"""

import sqlite3
import struct
from pathlib import Path

import numpy as np

_ENVELOPE_DOUBLES = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}  # flags bits 1-3 -> doubles after srs_id
_POLYGON, _MULTIPOLYGON = 3, 6


def connect(path):
    """A read-only connection (the file is never locked or written)."""
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro&immutable=1", uri=True)


def feature_tables(path):
    """{table: (geometry column, srs_id)} of the file's feature tables."""
    with connect(path) as db:
        rows = db.execute(
            "SELECT c.table_name, g.column_name, g.srs_id FROM gpkg_contents c "
            "JOIN gpkg_geometry_columns g ON g.table_name = c.table_name WHERE c.data_type = 'features'"
        ).fetchall()
    return {table: (column, srs) for table, column, srs in rows}


def read_polygons(path, table, columns, where=None):
    """Yield (attributes {column: value}, [polygon, ...]) per row of `table` (those matching the
    SQL condition `where`, if given), each polygon a list of (n, 2) float64 rings (x, y) as
    stored, shell first; an empty geometry gives []."""
    geometry, _ = feature_tables(path)[table]
    names = ", ".join(_quote(c) for c in (*columns, geometry))
    sql = f"SELECT {names} FROM {_quote(table)}" + (f" WHERE {where}" if where else "")
    with connect(path) as db:
        for row in db.execute(sql):
            blob = row[-1]
            yield dict(zip(columns, row[:-1], strict=True)), polygons(blob) if blob is not None else []


def polygons(blob):
    """The polygons of one GeoPackage geometry blob."""
    blob = memoryview(blob)
    if bytes(blob[:2]) != b"GP":
        raise ValueError("not a GeoPackage geometry (no 'GP' magic)")
    flags = blob[3]
    envelope = (flags >> 1) & 0b111
    if envelope not in _ENVELOPE_DOUBLES:
        raise ValueError(f"bad GeoPackage envelope indicator {envelope}")
    if flags & 0b10000:  # the empty-geometry flag
        return []
    return _wkb(blob, 8 + 8 * _ENVELOPE_DOUBLES[envelope])[0]


def _wkb(buf, at):
    """(polygons, next offset) for the WKB geometry at `at`."""
    order = "<" if buf[at] == 1 else ">"
    (code,) = struct.unpack_from(order + "I", buf, at + 1)
    at += 5
    kind, dims = _kind(code)
    if kind == _POLYGON:
        rings, at = _polygon(buf, at, order, dims)
        return ([rings] if rings else []), at
    if kind == _MULTIPOLYGON:
        (count,) = struct.unpack_from(order + "I", buf, at)
        at += 4
        out = []
        for _ in range(count):
            parts, at = _wkb(buf, at)
            out += parts
        return out, at
    raise ValueError(f"WKB geometry type {code} is not a polygon or multipolygon")


def _kind(code):
    """(base type, ordinates per vertex) for ISO (1003, 2003, 3003) and EWKB (flag bits) codes."""
    z, m = bool(code & 0x80000000), bool(code & 0x40000000)
    code &= 0x0FFFFFFF
    iso, base = divmod(code, 1000)
    z |= iso in (1, 3)
    m |= iso in (2, 3)
    return base, 2 + z + m


def _polygon(buf, at, order, dims):
    (count,) = struct.unpack_from(order + "I", buf, at)
    at += 4
    rings = []
    for _ in range(count):
        (n,) = struct.unpack_from(order + "I", buf, at)
        at += 4
        coords = np.frombuffer(buf, dtype=np.dtype(order + "f8"), count=n * dims, offset=at)
        at += 8 * n * dims
        rings.append(coords.reshape(n, dims)[:, :2].astype(np.float64))
    return rings, at


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'
