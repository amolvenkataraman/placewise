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
    iter_xml,
    local_name,
    new_points,
    parse_iso_time,
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
    """Tracks from a .kml or .kmz path, bytes or file object, one per track-bearing Placemark.
    The document is streamed: each Placemark is read when it ends and then dropped."""
    data = read_source(source)
    if data.startswith(ZIP_MAGIC):
        data = _kmz_document(data)
    origin = source_name(source, "kml")
    found, mismatched = [], 0
    stack, placemarks, root, count = [], [], None, 0
    for event, element in iter_xml(data):
        if root is None:
            root = local_name(element.tag)
        if root != kml.ROOT_ELEMENT:  # read on: malformed XML is reported before a wrong root
            element.clear()
            continue
        if event == "start":
            stack.append(element)
            if local_name(element.tag) == "Placemark":
                placemarks.append((count, element))  # numbered in document order
                count += 1
            continue
        stack.pop()
        if placemarks and placemarks[-1][1] is element:
            order, _ = placemarks.pop()
            track, bad = _read_placemark(element, origin)
            mismatched += bad
            if track is not None:
                found.append((order, track))
            if not placemarks and stack:  # an outer Placemark would still read this one's parts
                stack[-1].remove(element)
    if root != kml.ROOT_ELEMENT:
        raise ValueError(f"not KML: root element is <{root}>")
    warn_skipped(mismatched, "gx:Track(s)", "<when> and <gx:coord> counts differ", "KML")
    return [track for _, track in sorted(found, key=lambda pair: pair[0])]


def _read_placemark(placemark, origin):
    """(Track or None, number of gx:Tracks whose <when> and <gx:coord> counts differ)."""
    points = new_points(("ele",))  # the SimpleArray columns join when a gx:Track has one
    segments, mismatched = [], 0
    for part in placemark.iter():
        start = len(points["time"])
        kind = local_name(part.tag)
        if kind == "Track":
            mismatched += not _read_gx_track(part, points)
        elif kind == "LineString":
            _read_line_string(part, points)
        if len(points["time"]) > start:
            segments.append(start)
    if not points["time"]:
        return None, mismatched
    for column in _COLUMNS[1:]:  # NaN for the points of parts without the column
        if column in points:
            points[column].extend([math.nan] * (len(points["time"]) - len(points[column])))
    meta = TrackMeta(name=xml_text(xml_child(placemark, "name")), source=origin)
    return build_track(points, segments, meta), mismatched


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
    start = len(points["time"])
    for when, coord in zip(whens, coords, strict=True):
        points["time"].append(parse_iso_time(when) if when else math.nan)
        points["lon"].append(float(coord[0]))
        points["lat"].append(float(coord[1]))
        points["ele"].append(float(coord[2]) if len(coord) > 2 else math.nan)
    for column, values in arrays.items():
        column_values = points.setdefault(column, [])
        column_values.extend([math.nan] * (start - len(column_values)))  # earlier parts lacked it
        column_values.extend(values)
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
