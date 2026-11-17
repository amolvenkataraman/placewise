"""Writes the Natural Earth-like shapefile fixtures in data/ (run once; the output is committed).

    uv run python tests/packbuild/make_fixtures.py

Shapes are coarse boxes, not real borders. Attribute names follow Natural Earth 5.1.1.

The text fixtures beside them are excerpts of the real files with deliberate tweaks so one row
exercises each rule: alternatenames trimmed; Yosemite Valley's dem set to -9999 (no data) and its
admin1 (US.CA) left out of admin1CodesASCII.txt; airports.csv adds rows that must be dropped
(non-scheduled small airport, heliport, seaplane base, closed).
"""

from pathlib import Path

import shapefile  # pyshp

DATA = Path(__file__).parent / "data"
WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def box(south, west, north, east):
    """One clockwise ring in (lon, lat), as the shapefile spec wants outer rings."""
    return [[(west, south), (west, north), (east, north), (east, south), (west, south)]]


def write(name, fields, rows):
    base = DATA / name
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        for field in fields:
            w.field(*field)
        for rings, record in rows:
            w.poly(rings)
            w.record(*record)
    base.with_suffix(".prj").write_text(WGS84_PRJ)
    base.with_suffix(".cpg").write_text("UTF-8")


def countries():
    c = ("C", 80)
    fields = [
        ("ADM0_A3", *c), ("ISO_A2_EH", *c), ("ISO_A3_EH", *c), ("NAME", *c), ("NAME_EN", *c),
        ("SOVEREIGNT", *c), ("TYPE", *c), ("CONTINENT", *c), ("POP_EST", "N", 18, 0),
        ("ADM0_A3_US", *c), ("ADM0_A3_IN", *c), ("FCLASS_ISO", *c), ("FCLASS_US", *c), ("FCLASS_IN", *c),
    ]  # fmt: skip
    rows = [
        (box(41.7, -95.2, 56.9, -74.3), ("CAN", "CA", "CAN", "Canada", "Canada", "Canada",
         "Sovereign country", "North America", 37589262, "CAN", "CAN", "Admin-0 country",
         "Admin-0 country", "Admin-0 country")),
        (box(8.0, 68.0, 35.0, 97.0), ("IND", "IN", "IND", "India", "India", "India",
         "Sovereign country", "Asia", 1366417754, "IND", "IND", "Admin-0 country",
         "Admin-0 country", "Admin-0 country")),
        # no ISO code ("-99") and no English name: id and name fall back
        (box(8.0, 43.0, 11.5, 49.0), ("SOL", "-99", "-99", "Somaliland", "", "Somaliland",
         "Sovereign country", "Africa", 5096159, "SOL", "SOM", "Unrecognized", "Unrecognized",
         "Unrecognized")),
    ]  # fmt: skip
    write("ne_countries", fields, rows)


def admin1():
    c = ("C", 80)
    fields = [
        ("adm1_code", *c), ("iso_3166_2", *c), ("iso_a2", *c), ("adm0_a3", *c), ("name", *c),
        ("name_alt", *c), ("type_en", *c), ("FCLASS_ISO", *c), ("FCLASS_IN", *c),
    ]  # fmt: skip
    rows = [
        (box(41.7, -95.2, 56.9, -74.3), ("CAN-682", "CA-ON", "CA", "CAN", "Ontario", "Upper Canada",
         "Province", "Admin-1 states provinces", "Admin-1 states provinces")),
        (box(11.6, 74.0, 18.5, 78.6), ("IND-2446", "IN-KA", "IN", "IND", "Karnataka", "Maisur|Mysore",
         "State", "Admin-1 states provinces", "Admin-1 states provinces")),
        # Natural Earth's placeholder code for units without one: id falls back to adm1_code
        (box(8.0, 43.0, 11.5, 49.0), ("SOL+00?", "-99-X11~", "-1", "SOL", "Somaliland", "",
         "", "Unrecognized", "Unrecognized")),
        # the same ISO 3166-2 code on two features: neither may claim it
        (box(43.0, 16.0, 44.0, 17.0), ("BIH-4801", "BA-BIH", "BA", "BIH", "Unsko-Sanski", "",
         "Canton", "Admin-1 states provinces", "Admin-1 states provinces")),
        (box(44.0, 16.0, 45.0, 17.0), ("BIH-4802", "BA-BIH", "BA", "BIH", "Posavski", "",
         "Canton", "Admin-1 states provinces", "Admin-1 states provinces")),
    ]  # fmt: skip
    write("ne_admin1", fields, rows)


if __name__ == "__main__":
    countries()
    admin1()
