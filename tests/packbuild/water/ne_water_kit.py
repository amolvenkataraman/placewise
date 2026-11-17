"""Natural Earth-like water shapefiles written on the fly (pyshp): coarse boxes, real field names."""

import shapefile  # pyshp

MARINE_FIELDS = ("name", "name_en", "namealt", "featurecla", "wikidataid", "ne_id")
LAKE_FIELDS = ("name", "name_en", "name_alt", "featurecla", "wikidataid", "ne_id")
RIVER_FIELDS = ("name", "name_en", "name_full", "featurecla", "wikidataid", "ne_id", "scalerank")


def box(south, west, north, east):
    """A clockwise ring in (lon, lat), as the shapefile spec wants outer rings."""
    return [(west, south), (west, north), (east, north), (east, south), (west, south)]


def write_polygons(base, fields, rows):
    """rows: (rings, {field: value}); returns the .shp path."""
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        for f in fields:
            w.field(f, "C", 80)
        for rings, record in rows:
            w.poly(rings)
            w.record(*[str(record.get(f, "")) for f in fields])
    return base.with_suffix(".shp")


def write_lines(base, fields, rows):
    """rows: (lines, {field: value}); lines are lists of (lon, lat)."""
    with shapefile.Writer(str(base), shapeType=shapefile.POLYLINE, encoding="utf-8") as w:
        for f in fields:
            w.field(f, "C", 80)
        for lines, record in rows:
            w.line(lines)
            w.record(*[str(record.get(f, "")) for f in fields])
    return base.with_suffix(".shp")
