"""A small EEA Nationally designated areas GeoPackage and Wikidata WDPA-label result for tests.

Invented sites in the open Bay of Biscay (around 45°N 10°W), drawn in ETRS89-LAEA (EPSG:3035) like
the real file; country codes and designation types are the EEA's.
"""

import sqlite3

from gpkg_kit import gp_blob, wkb_multipolygon, write_gpkg

from packbuild.projection import ETRS89_LAEA

TYPES = [  # designationTypeCode, category, English name
    ("XX01", "A", "National Park"),
    ("XX02", "A", "Nature Park"),
    ("XX03", "A", "Nature Reserve"),
    ("XX04", "A", "Natura 2000 SCI"),
    ("EL96", "A", "National Park"),
]
# natDAId, country, type, IUCN, hectares, name, geometry type, box (south, west, north, east)
SITES = [
    (101, "XX", "XX01", "II", 30000, "Alpha", "polygon", (45.00, -10.00, 45.20, -9.80)),
    (102, "XX", "XX01", "II", 20000, "Nationalpark Alpha Kernzone", "polygon", (45.20, -10.00, 45.30, -9.80)),
    (103, "XX", "XX01", "II", 20000, "Beta", "polygon", (45.30, -10.00, 45.40, -9.80)),  # touches 102
    (104, "XX", "XX02", "V", 50000, "Delta Naturpark", "polygon", (44.50, -10.00, 44.80, -9.50)),
    (105, "XX", "XX03", "IV", 300, "2001221 Epsilon", "polygon", (44.40, -10.00, 44.42, -9.97)),
    (106, "XX", "XX03", "IV", 50, "Tiny Reserve", "polygon", (44.30, -10.00, 44.301, -9.999)),
    (107, "XX", "XX04", "", 9000, "Habitat Site", "polygon", (44.20, -10.00, 44.30, -9.90)),
    (108, "XX", "XX03", "IV", 900, "Point Reserve", "point", None),
    (109, "EL", "EL96", "II", 9000, "Ethniko Parko Zeta", "polygon", (44.00, -11.00, 44.10, -10.90)),
]
LABELS = [  # (qid, WDPA id, English label): an item for a site and a later one for its zone
    ("Q900", "101", "Alpha National Park"),
    ("Q90000", "101", "Nationalpark Alpha Aussenzone"),
    ("Q901", "999999", "Somewhere Else"),
]


def laea_ring(south, west, north, east, clockwise=False):
    corners = [(south, west), (south, east), (north, east), (north, west), (south, west)]
    if clockwise:
        corners = corners[::-1]
    return [tuple(map(float, ETRS89_LAEA.forward(lon, lat))) for lat, lon in corners]


def write_natda(folder):
    """(GeoPackage, Wikidata result) paths, as eea.fetch returns them."""
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for site, country, _, _, _, name, kind, box in SITES:
        if kind == "point":
            blob = gp_blob(b"\x01" + (1).to_bytes(4, "little") + bytes(16))  # a WKB point: never parsed
        else:
            shell = laea_ring(*box)  # counter-clockwise, as OGC writers do
            if site == 101:  # with a hole, drawn clockwise
                south, west = box[:2]
                hole = laea_ring(south + 0.05, west + 0.05, south + 0.1, west + 0.1, clockwise=True)
                blob = gp_blob(wkb_multipolygon([[shell, hole]]))
            else:
                blob = gp_blob(wkb_multipolygon([[shell]]))
        rows.append((site, name, country, kind, blob))
    path = write_gpkg(
        folder / "natda.gpkg", "ProtectedSite", ("natDAId", "siteName", "countryCode", "geomType"), rows
    )
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE DesignationType (designationTypeCode TEXT, designationTypeCategory TEXT, "
               "designationTypeNameEnglish TEXT)")  # fmt: skip
    db.executemany("INSERT INTO DesignationType VALUES (?, ?, ?)", TYPES)
    db.execute("CREATE TABLE DesignatedArea (natDAId INTEGER, natDACountryCode TEXT, "
               "designationTypeCode TEXT, iucnCategory TEXT, siteArea REAL)")  # fmt: skip
    db.executemany("INSERT INTO DesignatedArea VALUES (?, ?, ?, ?, ?)", [s[:5] for s in SITES])
    db.commit()
    db.close()
    lines = ["?wdpa\t?item\t?name"] + [
        f'"{w}"\t<http://www.wikidata.org/entity/{q}>\t"{n}"@en' for q, w, n in LABELS
    ]
    labels = folder / "wikidata"  # a QLever TSV export
    labels.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, labels
