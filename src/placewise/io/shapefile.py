"""ESRI shapefile polygons (.shp + .dbf attributes + .prj check) into Features, without dependencies.

Follows the ESRI Shapefile Technical Description (1998): polygon rings run clockwise for outer
boundaries and counter-clockwise for holes, and one record may hold several polygons.
Only WGS84 longitude/latitude files are accepted, matching placewise's scope; NAD83 (and its
realisations such as NAD83(2011) and NAD83(CSRS)) can be accepted explicitly, since in North America
it differs from WGS84 by 1-2 m, less than the generalisation of almost any boundary file.
"""

import re
import struct
from pathlib import Path

import numpy as np

from placewise.geo import shapes
from placewise.model import Feature, Outline

_POLYGON_TYPES = {5, 15, 25}  # Polygon, PolygonZ, PolygonM (Z and M values are ignored)
_NULL_SHAPE = 0


def read_shapefile(path, accept_nad83=False):
    """Features from a .shp path (attributes from the .dbf beside it when present). With
    accept_nad83, NAD83 longitude/latitude is read as WGS84 without transforming."""
    shp = Path(path).with_suffix(".shp")
    _check_prj(shp.with_suffix(".prj"), accept_nad83)
    dbf = shp.with_suffix(".dbf")
    records = list(_read_dbf(dbf, _encoding(shp.with_suffix(".cpg")))) if dbf.exists() else None
    features = []
    for i, rings in enumerate(_read_shp(shp)):
        if rings is not None:
            features.append(Feature(_group_rings(rings), records[i] if records else {}))
    return features


def _check_prj(prj, accept_nad83):
    if not prj.exists():
        return  # unlabelled files are taken as WGS84 lon/lat, the overwhelmingly common case
    datum = prj_datum(prj.read_text(encoding="utf-8", errors="replace"), name=prj.name)
    if datum == "nad83" and not accept_nad83:
        raise ValueError(f"{prj.name}: datum is NAD83, not WGS84; pass accept_nad83=True to read it as WGS84")


_DATUM = re.compile(r'DATUM\s*\[\s*"([^"]*)"', re.IGNORECASE)


def prj_datum(text, name=".prj"):
    """ "wgs84" or "nad83" for a geographic .prj; ValueError for projected files and other datums."""
    text = text.strip().upper()
    if text.startswith("PROJCS"):
        raise ValueError(f"{name}: projected coordinates; placewise reads WGS84 longitude/latitude only")
    match = _DATUM.search(text)
    # ESRI writes "D_WGS_1984"; other writers "WGS84" or "World Geodetic System 1984"
    datum = re.sub(r"[^A-Z0-9]", "", re.sub(r"^D_", "", match.group(1))) if match else ""
    if "WGS84" in datum or "WGS1984" in datum or "WORLDGEODETICSYSTEM1984" in datum:
        return "wgs84"
    if datum.startswith(("NAD83", "NAD1983", "NORTHAMERICAN1983", "NORTHAMERICANDATUM1983")):
        return "nad83"
    found = repr(match.group(1)) if match else "no datum"
    raise ValueError(
        f"{name}: datum is not WGS84 ({found}); other datums need a datum shift placewise doesn't do"
    )


def _encoding(cpg):
    return cpg.read_text().strip() if cpg.exists() else "utf-8"


def _read_shp(path):
    data = path.read_bytes()
    if len(data) < 100 or struct.unpack(">i", data[:4])[0] != 9994:
        raise ValueError(f"{path.name} is not a shapefile")
    offset = 100
    while offset + 8 <= len(data):
        content_words = struct.unpack(">i", data[offset + 4 : offset + 8])[0]
        start, offset = offset + 8, offset + 8 + 2 * content_words
        shape_type = struct.unpack("<i", data[start : start + 4])[0]
        if shape_type == _NULL_SHAPE:
            yield None
            continue
        if shape_type not in _POLYGON_TYPES:
            raise ValueError(f"{path.name}: shape type {shape_type} is not a polygon")
        n_parts, n_points = struct.unpack("<2i", data[start + 36 : start + 44])
        parts = np.frombuffer(data, "<i4", n_parts, start + 44)
        points = np.frombuffer(data, "<f8", 2 * n_points, start + 44 + 4 * n_parts).reshape(-1, 2)
        yield np.split(points, parts[1:])  # (x, y) = (lon, lat) per ring


def _signed_area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))  # > 0 counter-clockwise


def _group_rings(rings):
    """Outlines: each clockwise ring with the counter-clockwise holes that fall inside it."""
    latlon = [tuple(zip(r[:, 1].tolist(), r[:, 0].tolist(), strict=True)) for r in rings]
    outer = [i for i, r in enumerate(rings) if _signed_area(r) < 0]
    if not outer:  # some writers ignore winding: treat every ring as a polygon
        return tuple(Outline((ring,)) for ring in latlon)
    holes = {i: [] for i in outer}
    for i, ring in enumerate(rings):
        if i in holes:
            continue
        lat, lon = ring[0, 1], ring[0, 0]
        owner = next((o for o in outer if shapes.contains([latlon[o]], lat, lon)), outer[0])
        holes[owner].append(latlon[i])
    return tuple(Outline((latlon[o], *holes[o])) for o in outer)


def _read_dbf(path, encoding):
    data = path.read_bytes()
    n_records, header_len, record_len = struct.unpack("<IHH", data[4:12])
    fields, pos = [], 32
    while data[pos] != 0x0D:
        name = data[pos : pos + 11].split(b"\x00")[0].decode("ascii")
        fields.append((name, chr(data[pos + 11]), data[pos + 16], data[pos + 17]))
        pos += 32
    for r in range(n_records):
        record = data[header_len + r * record_len : header_len + (r + 1) * record_len]
        values, cursor = {}, 1  # byte 0 is the deletion flag
        for name, kind, length, decimals in fields:
            # some writers (Natural Earth) pad text with NUL bytes rather than the spaces dBASE specifies
            raw = record[cursor : cursor + length].decode(encoding, errors="replace").strip(" \t\r\n\x00")
            cursor += length
            values[name] = _dbf_value(raw, kind, decimals)
        yield values


def _dbf_value(raw, kind, decimals):
    if not raw:
        return None
    if kind in "NF":
        return int(raw) if decimals == 0 and "." not in raw else float(raw)
    if kind == "L":
        return raw.upper() in ("T", "Y")
    if kind == "D" and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw
