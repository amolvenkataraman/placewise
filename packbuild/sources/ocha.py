"""OCHA COD-AB (Common Operational Datasets, administrative boundaries) packages from HDX, CC BY 3.0
IGO: one shapefile per administrative level, in the "cod-enhanced" schema.

Each package's shapefile zip (`<iso3>_admin_boundaries.shp.zip`) holds `<iso3>_admin<n>.shp` per
level n, and for some countries `<iso3>_admin<n>_em.shp` as well: the same units edge-matched to
the UN international boundary, so neighbouring countries don't overlap; those are preferred. Each
record carries `adm<n>_name` (English or romanised), `adm<n>_name1..3` (other languages and
scripts), `adm<n>_pcode` and every ancestor's name and P-code (`adm<n-1>_pcode` ... `adm0_pcode`),
`valid_on`, `area_sqkm` and `center_lat/lon`. Viet Nam's adds `adm1_type_` ("Province", "City").
Files are WGS84 longitude/latitude; anything else is refused.

Some writers overflow numeric fields ("*****" in Viet Nam's center_lat): read as null here, where
placewise.io's reader refuses them.
"""

import re
import struct
from pathlib import Path

import numpy as np

from placewise.constants.codab import ID_PREFIX
from placewise.io.shapefile import _read_shp, prj_datum  # the record parser and the .prj check

SOURCE_PREFIX = "ocha-cod-ab-"
SHAPEFILE_PARTS = ("shp", "shx", "dbf", "prj", "cpg")
_TYPE_FIELDS = ("adm{n}_type", "adm{n}_type_")  # dBASE cuts names at 10 characters


def source_id(iso3):
    """The registry id of a country's COD-AB package: "ocha-cod-ab-lka"."""
    return f"{SOURCE_PREFIX}{iso3}"


def level_stem(names, iso3, n):
    """The shapefile stem for level n among a zip's member names: the edge-matched "_em" one when
    the package has it. KeyError if the level is missing."""
    for stem in (f"{iso3}_admin{n}_em", f"{iso3}_admin{n}"):
        if f"{stem}.shp" in names:
            return stem
    raise KeyError(
        f"no {iso3}_admin{n}.shp in the package (it has {sorted(n for n in names if n.endswith('.shp'))})"
    )


def members(names, iso3, levels):
    """The zip members levels 1..levels need (.shp, .shx, .dbf, .prj and .cpg where present)."""
    stems = [level_stem(names, iso3, n) for n in range(1, levels + 1)]
    return [f"{s}.{part}" for s in stems for part in SHAPEFILE_PARTS if f"{s}.{part}" in names]


def read_level(shp):
    """(attributes, rings) per record of one level's shapefile, rings as (n, 2) lon/lat arrays.
    Records without a shape are skipped."""
    shp = Path(shp).with_suffix(".shp")
    prj = shp.with_suffix(".prj")
    if not prj.exists():
        raise ValueError(f"{prj.name}: missing; COD-AB shapefiles say their CRS")
    if prj_datum(prj.read_text(encoding="utf-8", errors="replace"), name=prj.name) != "wgs84":
        raise ValueError(f"{prj.name}: not WGS84")
    cpg = shp.with_suffix(".cpg")
    encoding = cpg.read_text().strip() if cpg.exists() else "utf-8"
    records = read_dbf(shp.with_suffix(".dbf"), encoding)
    for rings, props in zip(_read_shp(shp), records, strict=True):
        if rings is not None:
            yield props, [np.asarray(r, dtype=np.float64) for r in rings]


def row(props, n):
    """The pack row of a level-n record: id codab:<P-code>, the English name ("" where the package
    has none: 65 of Sri Lanka's 14,043 Grama Niladhari divisions), the P-code, the parent unit's
    id (level n-1; none for ADM1), valid_on and, where the package has one, the unit type."""
    pcode = _text(props.get(f"adm{n}_pcode"))
    name = _text(props.get(f"adm{n}_name"))
    if not pcode:
        raise ValueError(f"ADM{n} record without a P-code: {props}")
    parent = _text(props.get(f"adm{n - 1}_pcode")) if n > 1 else ""
    if n > 1 and not parent:
        raise ValueError(f"ADM{n} {pcode}: no adm{n - 1}_pcode")
    kind = next((_text(props[f.format(n=n)]) for f in _TYPE_FIELDS if props.get(f.format(n=n))), "")
    return {
        "id": f"{ID_PREFIX}{pcode}",
        "name": name,
        "pcode": pcode,
        "parent": f"{ID_PREFIX}{parent}" if parent else "",
        "type": kind,
        "valid_on": _text(props.get("valid_on")),
    }


def read_dbf(path, encoding="utf-8"):
    """dBASE records as dicts; numbers that don't parse (overflow stars) are None."""
    data = Path(path).read_bytes()
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
            raw = record[cursor : cursor + length].decode(encoding, errors="replace").strip(" \t\r\n\x00")
            cursor += length
            values[name] = _value(raw, kind, decimals)
        yield values


_NUMBER = re.compile(r"[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")


def _value(raw, kind, decimals):
    if not raw:
        return None
    if kind in "NF":
        if not _NUMBER.fullmatch(raw):
            return None
        return int(raw) if decimals == 0 and "." not in raw and "e" not in raw.lower() else float(raw)
    return raw


def _text(value):
    return "" if value is None else " ".join(str(value).split())
