"""Read any supported track file, recognising its format from the content, not the file name.

FIT by the ".FIT" signature at byte 8, KMZ by the zip signature, GPX / TCX / KML by the XML root
element, GeoJSON by a leading "{", NMEA by "$GPGGA"-style sentences in its first lines, and CSV
otherwise.
"""

import os
import re
import xml.etree.ElementTree as ET

from placewise.constants import nmea, track_files
from placewise.tracks import Track

from ._track_common import local_name, read_source, xml_document

_NMEA_SENTENCE = re.compile(rf"\$(?:{'|'.join(nmea.TALKER_IDS)})[A-Z]{{3}},")
_NMEA_LINES_CHECKED = 20  # logs open with a few lines of banner or non-position sentences
_XML_CHUNK = 4096


def detect_format(data):
    """The format name of track file content: fit, kmz, gpx, tcx, kml, geojson, nmea or csv."""
    offset = track_files.FIT_MAGIC_OFFSET
    if data[offset : offset + len(track_files.FIT_MAGIC)] == track_files.FIT_MAGIC:
        return "fit"
    if data.startswith(track_files.ZIP_MAGIC):
        return "kmz"
    head = data[: _XML_CHUNK * 4].decode("utf-8", errors="replace").lstrip("﻿ \t\r\n")
    if not head:
        raise ValueError("empty input: nothing to detect")
    if head.startswith("<"):
        root = _xml_root(xml_document(data))
        if root not in track_files.XML_ROOTS:
            raise ValueError(f"unrecognised XML track format: root element <{root}>")
        return track_files.XML_ROOTS[root]
    if head.startswith("{"):
        return "geojson"
    lines = [line for line in head.splitlines() if line.strip()][:_NMEA_LINES_CHECKED]
    if any(_NMEA_SENTENCE.search(line) for line in lines):
        return "nmea"
    return "csv"


def read_track(path_or_bytes):
    """(tracks, format name) for a path, bytes or binary file object of any supported format.

    GPX gives its tracks then its routes; FIT its one track."""
    data = read_source(path_or_bytes)
    fmt = detect_format(data)
    # a path goes to the reader as a path, so TrackMeta.source keeps the file name
    source = path_or_bytes if isinstance(path_or_bytes, str | os.PathLike) else data
    return _as_tracks(_READERS[fmt](source)), fmt


def _xml_root(data):
    parser = ET.XMLPullParser(events=("start",))
    for start in range(0, len(data), _XML_CHUNK):  # the root can follow a long prolog or comment
        parser.feed(data[start : start + _XML_CHUNK])
        for _, element in parser.read_events():
            return local_name(element.tag)
    raise ValueError("XML without a root element")


def _read_gpx(source):
    from placewise.io.gpx import read_gpx  # imported late: optional at import time of this module

    return read_gpx(source)


def _read_fit(source):
    from placewise.io.fit import read_fit

    return read_fit(source)


def _read_tcx(source):
    from .tcx import read_tcx

    return read_tcx(source)


def _read_kml(source):
    from .kml import read_kml

    return read_kml(source)


def _read_geojson(source):
    from .geojson_tracks import read_geojson_tracks

    return read_geojson_tracks(source)


def _read_nmea(source):
    from .nmea import read_nmea

    return read_nmea(source)


def _read_csv(source):
    from .csv_tracks import read_csv_track

    return read_csv_track(source)


_READERS = {
    "fit": _read_fit,
    "kmz": _read_kml,
    "gpx": _read_gpx,
    "tcx": _read_tcx,
    "kml": _read_kml,
    "geojson": _read_geojson,
    "nmea": _read_nmea,
    "csv": _read_csv,
}


def _as_tracks(result):
    """A list of Tracks from whatever a reader returns: a Track, a list, or a file object holding
    `tracks` (and `routes`) or a single `track`, as the GPX and FIT readers do."""
    if isinstance(result, Track):
        return [result]
    if hasattr(result, "tracks"):
        return [*result.tracks, *getattr(result, "routes", ())]
    if hasattr(result, "track"):
        return [result.track]
    return list(result)
