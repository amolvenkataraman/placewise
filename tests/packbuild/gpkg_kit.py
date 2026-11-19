"""Tiny GeoPackages for tests: the tables a reader needs and geometries packed as GP + WKB."""

import sqlite3
import struct


def wkb_polygon(rings, order="<", z=False):
    """WKB Polygon (ISO 1003 with z) of rings [(x, y), ...]."""
    out = struct.pack(order + "BII", 1 if order == "<" else 0, 1003 if z else 3, len(rings))
    for ring in rings:
        out += struct.pack(order + "I", len(ring))
        for x, y in ring:
            out += struct.pack(order + ("ddd" if z else "dd"), x, y, *((7.0,) if z else ()))
    return out


def wkb_multipolygon(polygons, order="<", z=False):
    head = struct.pack(order + "BII", 1 if order == "<" else 0, 1006 if z else 6, len(polygons))
    return head + b"".join(wkb_polygon(p, order, z) for p in polygons)


def gp_blob(wkb, srs_id=3035, envelope=(0.0, 1.0, 0.0, 1.0), empty=False):
    """GeoPackage geometry: magic, version 0, flags (little-endian header, xy envelope), srs_id."""
    flags = 0b1 | (0b10 if envelope else 0) | (0b10000 if empty else 0)
    head = b"GP" + bytes([0, flags]) + struct.pack("<i", srs_id)
    if envelope:
        head += struct.pack("<4d", *envelope)
    return head + wkb


def write_gpkg(path, table, columns, rows, geometry="geom", srs_id=3035):
    """A GeoPackage with one feature table: rows are (values..., blob or None)."""
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT, identifier TEXT)")
    db.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, "
               "geometry_type_name TEXT, srs_id INTEGER, z INTEGER, m INTEGER)")  # fmt: skip
    db.execute("INSERT INTO gpkg_contents VALUES (?, 'features', ?)", (table, table))
    db.execute("INSERT INTO gpkg_geometry_columns VALUES (?, ?, 'MULTIPOLYGON', ?, 0, 0)",
               (table, geometry, srs_id))  # fmt: skip
    cols = ", ".join(f'"{c}"' for c in (*columns, geometry))
    db.execute(f'CREATE TABLE "{table}" (fid INTEGER PRIMARY KEY, {cols})')
    marks = ", ".join("?" for _ in range(len(columns) + 1))
    db.executemany(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', rows)
    db.commit()
    db.close()
    return path
