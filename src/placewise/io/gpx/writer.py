"""Writing GPX 1.1, column by column (the extensions used are in the package's docstring)."""

import math
from itertools import pairwise
from pathlib import Path

import numpy as np

from placewise.constants.gpx import (
    GARMIN_POWER_NS,
    GARMIN_POWER_XSD,
    GARMIN_TPX_V2_NS,
    GARMIN_TPX_V2_XSD,
    GPX_11_NS,
    GPX_11_XSD,
    PLACEWISE_NS,
)
from placewise.tracks import Track

from .values import attribute, decimal, escape, format_time, integer

_CHUNK = 8192  # points formatted at a time when writing, so memory tracks the output, not columns


def write_gpx(tracks, path_or_none, waypoints=(), creator="placewise"):
    """GPX 1.1 text for a Track or iterable of Tracks (and Waypoints); also written to the path
    when one is given. NaN values (time included) are left out of the file."""
    if isinstance(tracks, Track):
        tracks = (tracks,)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<gpx version="1.1" creator={attribute(creator)} xmlns="{GPX_11_NS}"'
        f' xmlns:gpxtpx="{GARMIN_TPX_V2_NS}" xmlns:gpxpx="{GARMIN_POWER_NS}"'
        f' xmlns:placewise="{PLACEWISE_NS}"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' xsi:schemaLocation="{GPX_11_NS} {GPX_11_XSD} {GARMIN_TPX_V2_NS} {GARMIN_TPX_V2_XSD}'
        f' {GARMIN_POWER_NS} {GARMIN_POWER_XSD}">\n'
    ]
    for w in waypoints:
        parts.append(f'<wpt lat="{decimal(w.lat)}" lon="{decimal(w.lon)}">')
        if w.ele is not None and math.isfinite(w.ele):
            parts.append(f"<ele>{decimal(w.ele)}</ele>")
        if w.time is not None and math.isfinite(w.time):
            parts.append(f"<time>{format_time(w.time)}</time>")
        if w.name:
            parts.append(f"<name>{escape(w.name)}</name>")
        if w.desc:
            parts.append(f"<desc>{escape(w.desc)}</desc>")
        parts.append("</wpt>\n")
    for track in tracks:
        _write_track(track, parts)
    parts.append("</gpx>\n")
    if path_or_none is not None:
        with Path(path_or_none).open("w", encoding="utf-8", newline="") as f:
            f.writelines(parts)
    return "".join(parts)


# (column, element, formatter) in the order the elements appear; tpx = Garmin TrackPointExtension v2
_PLAIN = (("ele", "ele"), ("time", "time"), ("satellites", "sat"))
_TPX = (
    ("temperature", "atemp"),
    ("hr", "hr"),
    ("cadence", "cad"),
    ("speed", "speed"),
    ("heading", "course"),
)
_INTEGER_COLUMNS = frozenset(("hr", "cadence", "satellites"))  # unsignedByte / nonNegativeInteger


def _write_track(track, parts):
    parts.append("<trk>")
    if track.meta.name:
        parts.append(f"<name>{escape(track.meta.name)}</name>")
    if track.meta.activity:
        parts.append(f"<type>{escape(track.meta.activity)}</type>")
    parts.append("\n")
    n = len(track)
    present = set(track.columns)
    plain = [(c, e) for c, e in _PLAIN if c in present]
    tpx = [(c, e) for c, e in _TPX if c in present]
    bounds = (*track.segments, n) if n else (0, 0)
    for start, end in pairwise(bounds):
        parts.append("<trkseg>\n")
        for chunk in range(start, end, _CHUNK):
            parts.append(_format_points(track, slice(chunk, min(chunk + _CHUNK, end)), plain, tpx, present))
        parts.append("</trkseg>\n")
    parts.append("</trk>\n")


def _format_points(track, rows, plain, tpx, present):
    """The <trkpt> lines of `rows`, built column by column: each column's text for every point,
    then one join per point."""

    def strings(column):
        return _strings(getattr(track, column)[rows], column)

    def fragments(start, end, texts):
        return [f"{start}{t}{end}" if t is not None else "" for t in texts]

    lat, lon = _decimal_strings(track.lat[rows]), _decimal_strings(track.lon[rows])
    n = len(lat)
    columns = [[f'<trkpt lat="{a}" lon="{b}">' for a, b in zip(lat, lon, strict=True)]]
    columns += [fragments(f"<{e}>", f"</{e}>", strings(c)) for c, e in plain]
    inner = [fragments(f"<gpxtpx:{e}>", f"</gpxtpx:{e}>", strings(c)) for c, e in tpx]
    in_tpx = [any(texts) for texts in zip(*inner, strict=True)] if inner else [False] * n
    extra = []
    if "power" in present:
        extra.append(fragments("<gpxpx:PowerInWatts>", "</gpxpx:PowerInWatts>", strings("power")))
    if "accuracy" in present:
        extra.append(fragments("<placewise:accuracy>", "</placewise:accuracy>", strings("accuracy")))
    in_extensions = [any(flags) for flags in zip(in_tpx, *extra, strict=True)]
    columns.append(["<extensions>" if f else "" for f in in_extensions])
    columns.append(["<gpxtpx:TrackPointExtension>" if f else "" for f in in_tpx])
    columns += inner
    columns.append(["</gpxtpx:TrackPointExtension>" if f else "" for f in in_tpx])
    columns += extra
    columns.append(["</extensions></trkpt>\n" if f else "</trkpt>\n" for f in in_extensions])
    return "".join(map("".join, zip(*columns, strict=True)))


def _strings(values, column):
    """Text of each value as the file holds it, None for NaN."""
    if column == "time":
        return _time_strings(values)
    if column in _INTEGER_COLUMNS:
        return _integer_strings(values)
    return _decimal_strings(values)


def _decimal_strings(values):
    """decimal of each value, None for NaN."""
    texts = [t[:-2] if t.endswith(".0") else t for t in map(repr, values.tolist())]
    for k in [k for k, t in enumerate(texts) if "e" in t]:
        texts[k] = decimal(float(values[k]))
    return _nan_to_none(texts, values)


def _integer_strings(values):
    """integer of each value, None for NaN."""
    finite = values[~np.isnan(values)]
    if len(finite) and not np.all(np.abs(finite) < 2**52):  # inf, or past exact integers
        return [None if v != v else integer(v) for v in values.tolist()]
    # np.rint rounds half to even, as round() does
    texts = list(map(str, np.rint(np.nan_to_num(values)).astype(np.int64).tolist()))
    return _nan_to_none(texts, values)


_LAST_ISO_SECOND = 253402300799  # 9999-12-31T23:59:59, the last second datetime can print


def _time_strings(values):
    """format_time of each value, None for NaN."""
    finite = values[~np.isnan(values)]
    if len(finite) and not (np.all(finite >= 0) and np.all(finite <= _LAST_ISO_SECOND)):
        return [None if v != v else format_time(v) for v in values.tolist()]
    values0 = np.nan_to_num(values)
    whole = np.floor(values0)
    micro = np.round((values0 - whole) * 1e6)  # half to even, as round() does
    carry = micro == 1_000_000
    whole, micro = np.where(carry, whole + 1, whole), np.where(carry, 0.0, micro)
    texts = [t + "Z" for t in whole.astype("datetime64[s]").astype(str).tolist()]
    for k in np.flatnonzero(micro).tolist():
        texts[k] = texts[k][:-1] + f".{int(micro[k]):06d}".rstrip("0") + "Z"
    return _nan_to_none(texts, values)


def _nan_to_none(texts, values):
    for k in np.flatnonzero(np.isnan(values)).tolist():
        texts[k] = None
    return texts
