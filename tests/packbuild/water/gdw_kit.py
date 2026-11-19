"""A Global Dam Watch-like archive (pyshp + zipfile): reservoir boxes with the real field names,
in the real archive's folder."""

import zipfile

import shapefile  # pyshp

STEM = "GDW_reservoirs_v1_0"
FOLDER = "GDW_v1_0_shp"

# GDW_ID, RES_NAME, DAM_NAME, ALT_NAME, LAKE_CTRL, AREA_POLY (km²), (south, west, north, east)
RESERVOIRS = [
    (141, "Lake Tahoe", "Lake Tahoe", "", "Yes", 496.0, (38.9, -120.2, 39.25, -119.9)),  # a lake
    (336, "Hirakud", "Hirakud", "", "", 499.5, (20.5, 83.5, 21.8, 84.0)),
    (1687, "", "Tehri", "", "", 18.9, (30.35, 78.40, 30.45, 78.55)),
    (351, "Nagarjuna", "Nagarjuna Sagar", "", "", 195.2, (16.3, 79.0, 16.6, 79.3)),
    (11543, "", "BIG MEADOWS - MAIN DAM", "", "", 12.0, (40.0, -110.0, 40.05, -109.95)),
    (900, "", "", "", "", 50.0, (5.0, 5.0, 5.1, 5.1)),  # no name at all
    (901, "Tiny Reservoir", "Tiny", "", "", 3.0, (6.0, 6.0, 6.01, 6.01)),  # below the size kept
]


def _ring(south, west, north, east):
    return [(west, south), (west, north), (east, north), (east, south), (west, south)]


def write_archive(folder, rows=RESERVOIRS):
    """The archive as figshare serves it (barriers left out), named like its download URL."""
    base = folder / STEM
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        w.field("GDW_ID", "N", 9, 0)
        for name in ("RES_NAME", "DAM_NAME", "ALT_NAME", "LAKE_CTRL"):
            w.field(name, "C", 60)
        w.field("AREA_POLY", "N", 13, 3)
        for gid, res, dam, alt, ctrl, area, box in rows:
            w.poly([_ring(*box)])
            w.record(gid, res, dam, alt, ctrl, area)
    archive = folder / "47913754"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("GDW_TechDoc_v1_0.pdf", b"%PDF-1.4")
        for ext in (".dbf", ".shp", ".shx"):
            z.write(base.with_suffix(ext), f"{FOLDER}/{STEM}{ext}")
    for ext in (".dbf", ".shp", ".shx", ".cpg"):
        base.with_suffix(ext).unlink(missing_ok=True)
    return archive
