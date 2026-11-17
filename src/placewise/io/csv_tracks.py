"""CSV tracks in and out: one row per point, columns found by header name or given explicitly.

Times may be ISO 8601 (with or without an offset), unix seconds, unix milliseconds or anything a
strptime format describes; a time without an offset is taken as UTC.
"""

import csv
import io
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from placewise.constants import track_files
from placewise.tracks import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, TrackMeta

from ._track_common import (
    build_track,
    decode_text,
    format_iso_time,
    new_points,
    parse_iso_time,
    read_source,
    source_name,
    warn_skipped,
)

_UNITS = re.compile(r"[(\[].*?[)\]]")
_SEPARATORS = re.compile(r"[\s\-]+")


def read_csv_track(source, columns=None, time_format=None):
    """A Track from a CSV path, bytes or file object.

    `columns` maps Track column names to CSV headers ({"lat": "Y", "lon": "X", ...}); it overrides
    the auto-detection for the columns it names. `time_format` is a strptime format for the time
    column; without it times are read as ISO 8601 or unix seconds / milliseconds. Rows without a
    usable latitude and longitude are skipped; a TrackReadWarning reports how many."""
    text = decode_text(read_source(source))
    first_line = text.split("\n", 1)[0]
    delimiter = max(track_files.CSV_DELIMITERS, key=first_line.count)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)  # keeps quoted newlines
    header = next(reader, None)
    if header is None:
        raise ValueError("empty CSV: no header row")
    index = _column_index(header, columns)
    # with ";" as the separator a "," is free to be the decimal mark, as European tools write it
    decimal_comma = delimiter != ","
    points = new_points(OPTIONAL_COLUMNS)
    segment_ids, skipped = [], 0
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        lat, lon = _cell(row, index["lat"], decimal_comma), _cell(row, index["lon"], decimal_comma)
        if not (math.isfinite(lat) and math.isfinite(lon)):
            skipped += 1
            continue
        points["lat"].append(lat)
        points["lon"].append(lon)
        time_text = _raw(row, index.get("time"))
        points["time"].append(_parse_time(time_text, time_format) if time_text else math.nan)
        for name in OPTIONAL_COLUMNS:
            points[name].append(_cell(row, index.get(name), decimal_comma))
        segment_ids.append(_raw(row, index.get("segment")))
    warn_skipped(skipped, "row(s)", "no usable latitude / longitude", "CSV")
    segments = [i for i, s in enumerate(segment_ids) if i == 0 or s != segment_ids[i - 1]]
    return build_track(points, segments, TrackMeta(source=source_name(source, "csv")))


def _normalise(name):
    return _SEPARATORS.sub("_", _UNITS.sub("", name).strip().lower()).strip("_")


def _column_index(header, columns):
    index = {}
    normalised = [_normalise(h) for h in header]
    for column, aliases in track_files.CSV_HEADER_ALIASES.items():
        found = next((normalised.index(a) for a in aliases if a in normalised), None)
        if found is not None:
            index[column] = found
    found = next((normalised.index(a) for a in track_files.CSV_SEGMENT_HEADERS if a in normalised), None)
    if found is not None:
        index["segment"] = found
    for column, name in (columns or {}).items():
        if column not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
            raise ValueError(
                f"{column!r} is not a track column; known: {REQUIRED_COLUMNS + OPTIONAL_COLUMNS}"
            )
        if name not in header:
            raise ValueError(f"CSV has no column {name!r}; its headers are {header}")
        index[column] = header.index(name)
    if "lat" not in index or "lon" not in index:
        raise ValueError(
            f"CSV needs latitude and longitude columns; found headers {header}. "
            "Name them with columns={'lat': ..., 'lon': ...}"
        )
    return index


def _raw(row, i):
    if i is None or i >= len(row):
        return None
    return row[i].strip() or None


def _cell(row, i, decimal_comma):
    text = _raw(row, i)
    if text is None:
        return math.nan
    try:
        return float(text)
    except ValueError:
        if decimal_comma and text.count(",") == 1:
            try:
                return float(text.replace(",", "."))
            except ValueError:
                pass
        return math.nan


def _parse_time(text, time_format):
    if time_format is not None:
        parsed = datetime.strptime(text, time_format)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    try:
        value = float(text)
    except ValueError:
        return parse_iso_time(text)
    return value / 1000 if abs(value) > track_files.UNIX_MILLISECONDS_ABOVE else value


def write_csv_track(track, path):
    """Write a Track as CSV: ISO 8601 UTC times, then lat, lon and its other columns; a `segment`
    column is added when the track has more than one segment. Missing values are empty cells."""
    names = [n for n in track.columns if n != "time"]
    with_segments = len(track.segments) > 1
    segment_of = np.searchsorted(np.asarray(track.segments), np.arange(len(track)), side="right") - 1
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time", *names, *(["segment"] if with_segments else [])])
        for i in range(len(track)):
            row = [format_iso_time(float(track.time[i])) or ""]
            row += [_format(getattr(track, n)[i]) for n in names]
            if with_segments:
                row.append(int(segment_of[i]))
            writer.writerow(row)


def _format(value):
    value = float(value)
    if math.isnan(value):
        return ""
    # repr is the shortest text that reads back to the same float
    return str(int(value)) if value.is_integer() else repr(value)
