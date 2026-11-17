"""KML and KMZ tracks: gx:Track (and KML 2.3's Track), gx:MultiTrack and LineString placemarks.

Each Placemark holding a track geometry becomes one Track, named after the Placemark; the parts of a
MultiTrack or MultiGeometry become segments. LineStrings carry no times, so theirs are NaN.
"""

import io
import math
import re
import zipfile

from placewise.constants import kml
from placewise.constants.track_files import ZIP_MAGIC
from placewise.tracks import TrackMeta

from ._track_common import (
    build_track,
    local_name,
    new_points,
    parse_iso_time,
    parse_xml,
    read_source,
    source_name,
    to_float,
    warn_skipped,
    xml_child,
    xml_children,
    xml_text,
)

_COLUMNS = ("ele", *dict.fromkeys(kml.SIMPLE_ARRAY_COLUMNS.values()))
_COMMA_SPACING = re.compile(r"\s*,\s*")


def read_kml(source):
    """Tracks from a .kml or .kmz path, bytes or file object, one per track-bearing Placemark."""
    data = read_source(source)
    if data.startswith(ZIP_MAGIC):
        data = _kmz_document(data)
    root = parse_xml(data)
    if local_name(root.tag) != kml.ROOT_ELEMENT:
        raise ValueError(f"not KML: root element is <{local_name(root.tag)}>")
    origin = source_name(source, "kml")
    tracks, mismatched = [], 0
    for placemark in (e for e in root.iter() if local_name(e.tag) == "Placemark"):
        points = new_points(_COLUMNS)
        segments = []
        for part in placemark.iter():
            start = len(points["time"])
            kind = local_name(part.tag)
            if kind == "Track":
                mismatched += not _read_gx_track(part, points)
            elif kind == "LineString":
                _read_line_string(part, points)
            if len(points["time"]) > start:
                segments.append(start)
        if points["time"]:
            meta = TrackMeta(name=xml_text(xml_child(placemark, "name")), source=origin)
            tracks.append(build_track(points, segments, meta))
    warn_skipped(mismatched, "gx:Track(s)", "<when> and <gx:coord> counts differ", "KML")
    return tracks


def _kmz_document(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
        if not names:
            raise ValueError("KMZ archive holds no .kml document")
        # doc.kml by convention; otherwise the shallowest .kml, as Google Earth does
        main = (
            kml.KMZ_MAIN_DOCUMENT
            if kml.KMZ_MAIN_DOCUMENT in names
            else min(names, key=lambda n: n.count("/"))
        )
        return archive.read(main)


def _read_gx_track(track, points):
    whens = [xml_text(e) for e in xml_children(track, "when")]
    coords = [(xml_text(e) or "").split() for e in xml_children(track, "coord")]
    if len(whens) != len(coords):
        return False
    arrays = _simple_arrays(track, len(coords))
    for i, (when, coord) in enumerate(zip(whens, coords, strict=True)):
        points["time"].append(parse_iso_time(when) if when else math.nan)
        points["lon"].append(float(coord[0]))
        points["lat"].append(float(coord[1]))
        points["ele"].append(float(coord[2]) if len(coord) > 2 else math.nan)
        for column in _COLUMNS[1:]:
            points[column].append(arrays[column][i] if column in arrays else math.nan)
    return True


def _simple_arrays(track, n):
    arrays = {}
    for schema_data in xml_children(xml_child(track, "ExtendedData"), "SchemaData"):
        for array in xml_children(schema_data, "SimpleArrayData"):
            column = kml.SIMPLE_ARRAY_COLUMNS.get((array.get("name") or "").lower())
            values = [to_float(xml_text(v)) for v in xml_children(array, "value")]
            if column and len(values) == n:  # a short array can't be lined up with its points, so drop it
                arrays[column] = values
    return arrays


def _read_line_string(line, points):
    text = xml_text(xml_child(line, "coordinates")) or ""
    # the spec forbids spaces around the commas, but hand-edited files have them
    for chunk in _COMMA_SPACING.sub(",", text).split():
        values = chunk.split(",")
        points["time"].append(math.nan)
        points["lon"].append(float(values[0]))
        points["lat"].append(float(values[1]))
        points["ele"].append(float(values[2]) if len(values) > 2 else math.nan)
        for column in _COLUMNS[1:]:
            points[column].append(math.nan)
