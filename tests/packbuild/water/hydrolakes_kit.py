"""A HydroLAKES-like archive (pyshp + zipfile): a few boxes, largest first like the real file,
and an opener serving its byte ranges as HTTP range requests would."""

import zipfile

import shapefile  # pyshp

URL = "https://example.org/HydroLAKES_polys_v10_shp.zip"
STEM = "HydroLAKES_polys_v10"

# Hylak_id, Lake_name, Lake_type, Lake_area (km²), (south, west, north, east)
LAKES = [
    (1, "Ontario", 1, 19347.36, (43.2, -79.8, 44.2, -76.1)),
    (2, "", 2, 500.81, (20.5, 83.5, 21.8, 84.0)),  # unnamed reservoir (Natural Earth names it)
    (3, "Tahoe", 1, 495.62, (38.9, -120.2, 39.25, -119.9)),
    (4, "", 1, 11.7, (34.08, 74.84, 34.14, 74.89)),  # unnamed (Wikidata names it)
    (5, "", 1, 10.5, (10.0, 10.0, 10.03, 10.03)),  # unnamed everywhere: left out
    (6, "Small", 1, 3.0, (50.0, 10.0, 50.01, 10.01)),  # below the size kept
    (7, "", 1, 0.5, (51.0, 10.0, 51.005, 10.005)),
]


def _ring(south, west, north, east):
    return [(west, south), (west, north), (east, north), (east, south), (west, south)]


def write_archive(folder):
    base = folder / STEM
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        w.field("Hylak_id", "N", 9, 0)
        w.field("Lake_name", "C", 40)
        w.field("Country", "C", 35)
        w.field("Lake_type", "N", 4, 0)
        w.field("Lake_area", "N", 13, 2)
        for hylak, name, kind, area, box in LAKES:
            w.poly([_ring(*box)])
            w.record(hylak, name, "United States of America", kind, area)
    base.with_suffix(".prj").write_text('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]]')
    archive = folder / "HydroLAKES_polys_v10_shp.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{STEM}_shp/", "")
        for ext in (".dbf", ".prj", ".shp", ".shx"):
            z.write(base.with_suffix(ext), f"{STEM}_shp/{STEM}{ext}")
    for ext in (".dbf", ".prj", ".shp", ".shx", ".cpg"):
        base.with_suffix(ext).unlink(missing_ok=True)
    return archive


def opener_for(archive, served=None, url=URL):
    data = archive.read_bytes()

    def opener(asked, first, last):
        assert asked == url
        start = len(data) + first if first < 0 else first
        stop = len(data) if last is None else last + 1
        if served is not None:
            served.append((start, stop))
        return iter([data[start:stop]]), len(data)

    return opener
