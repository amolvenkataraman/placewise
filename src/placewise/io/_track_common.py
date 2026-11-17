"""Shared plumbing for the track readers: loading a source, ISO 8601 times, skip warnings and
building a Track from per-point lists."""

import calendar
import math
import os
import re
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from placewise.tracks import OPTIONAL_COLUMNS, Track

# datetime.fromisoformat only takes "Z" and arbitrary fraction lengths from 3.11, so parse by hand
_ISO = re.compile(
    r"\s*(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?)?"
    r"\s*(Z|[+-]\d{2}(?::?\d{2})?)?\s*$",
    re.IGNORECASE,
)


class TrackReadWarning(UserWarning):
    """Points or sentences a reader dropped; `skipped` is how many and `reason` why."""

    def __init__(self, message, skipped=0, reason=None):
        super().__init__(message)
        self.skipped = skipped
        self.reason = reason


def warn_skipped(skipped, what, reason, fmt):
    if skipped:
        warnings.warn(
            TrackReadWarning(f"{fmt}: skipped {skipped} {what} ({reason})", skipped, reason), stacklevel=3
        )


def read_source(source):
    """Bytes from raw bytes, a binary or text file object, or a path (str or PathLike)."""
    if isinstance(source, bytes | bytearray | memoryview):
        return bytes(source)
    if hasattr(source, "read"):
        data = source.read()
        return data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return Path(source).read_bytes()


def source_name(source, default):
    """The file name for TrackMeta.source when the source is a path, else the format name."""
    if isinstance(source, str | os.PathLike):
        return Path(source).name
    name = getattr(source, "name", None)
    return Path(name).name if isinstance(name, str) else default


def decode_text(data):
    # utf-8-sig drops the BOM that Windows tools put at the front of CSV and NMEA logs
    return data.decode("utf-8-sig", errors="replace")


def parse_iso_time(text):
    """UTC unix seconds from an ISO 8601 date-time; a missing offset is taken as UTC."""
    match = _ISO.match(text)
    if not match:
        raise ValueError(f"not an ISO 8601 time: {text!r}")
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    seconds = calendar.timegm(
        (int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0), 0, 0, 0)
    )
    if fraction:
        seconds += float(fraction)
    if zone and zone.upper() != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        offset = int(digits[:2]) * 3600 + (int(digits[2:4]) * 60 if len(digits) > 2 else 0)
        seconds -= sign * offset
    return float(seconds)


def format_iso_time(seconds):
    """ISO 8601 in UTC with a Z; milliseconds only when the time has a fraction."""
    if not math.isfinite(seconds):
        return None
    whole = math.floor(seconds)
    millis = round((seconds - whole) * 1000)
    if millis == 1000:
        whole, millis = whole + 1, 0
    stamp = datetime.fromtimestamp(whole, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{stamp}.{millis:03d}Z" if millis else f"{stamp}Z"


def to_float(text):
    """A float from a text field; blank or unparsable gives NaN."""
    if text is None:
        return math.nan
    try:
        return float(text)
    except (TypeError, ValueError):
        return math.nan


def build_track(points, segments, meta):
    """A Track from a dict of per-point lists (time, lat, lon and optional columns); optional
    columns with no value at all are left out rather than kept as all-NaN."""
    columns = {"time": points["time"], "lat": points["lat"], "lon": points["lon"]}
    for name in OPTIONAL_COLUMNS:
        values = points.get(name)
        if values is not None and len(values) and not np.all(np.isnan(np.asarray(values, dtype=float))):
            columns[name] = values
    return Track.from_columns(columns, segments if points["time"] else None, meta)


def new_points(names=OPTIONAL_COLUMNS):
    return {"time": [], "lat": [], "lon": [], **{n: [] for n in names}}


def xml_document(data):
    """The bytes from the first "<" on: exporters leave a BOM or blank lines before the XML
    declaration, which expat refuses."""
    start = data.find(b"<")
    return data[start:] if start > 0 and not data[:start].strip(b"\xef\xbb\xbf \t\r\n") else data


def parse_xml(data):
    """The root element; malformed XML raises ValueError like every other bad input, not ParseError."""
    try:
        return ET.fromstring(xml_document(data))
    except ET.ParseError as error:
        raise ValueError(f"not well-formed XML: {error}") from None


# XML formats come with several namespace versions (and sometimes none), so match on local names
def local_name(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def xml_child(element, name):
    if element is None:
        return None
    for child in element:
        if local_name(child.tag) == name:
            return child
    return None


def xml_children(element, name):
    return [] if element is None else [c for c in element if local_name(c.tag) == name]


def xml_text(element):
    if element is None or element.text is None:
        return None
    return element.text.strip() or None
