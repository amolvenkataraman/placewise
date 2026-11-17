"""GPX 1.0 / 1.1 tracks, routes and waypoints in and out, streamed with ElementTree.iterparse.

Reading:

- namespaces are ignored (GPX 1.0, 1.1 and namespace-less files read alike); extension elements
  are matched by local name, so Garmin TrackPointExtension v1 and v2, Garmin PowerExtension and
  the bare `<power>` some apps write all land in the same columns;
- `<time>` is ISO 8601 (Z, numeric offsets, any number of fractional digits); a time without a
  zone is UTC, as the GPX schema defines. A point without a time, or with an unreadable one, gets
  NaN, so a track recorded without a clock has an all-NaN `time` column;
- `<hdop>` is a unitless dilution of precision, not metres, so it never fills `accuracy`. It is
  returned beside the tracks in `GpxFile.track_hdop` / `route_hdop`; multiply by the receiver's
  error (UERE, a few metres for phones) for a rough accuracy if one is needed;
- points whose lat/lon are missing, out of range, not plain decimals (xsd:decimal has no exponent,
  so "1.2E-5" is a logger bug) or exactly 0,0 (a receiver without a fix) are dropped and counted
  in `GpxFile.skipped`. A segment left empty by this disappears;
- `meta.activity` is the track's `<type>`, else an `Activity = ...` comment as BasicAirData GPS
  Logger writes, else the file's `<metadata><keywords>`. `meta.name` falls back to the file's
  `<metadata><name>`; `meta.device` is the `creator` attribute.

Writing produces GPX 1.1: speed, course, hr, cadence and temperature go in Garmin
TrackPointExtension v2, power in Garmin PowerExtension, accuracy (metres) in a placewise extension.
hr, cadence and satellites are integers in their schemas and are rounded.
"""

import datetime as dt
import io
import math
import re
import xml.etree.ElementTree as ET
from array import array
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import pairwise, repeat
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from placewise.constants.gpx import (
    EXTENSION_ELEMENTS,
    GARMIN_POWER_NS,
    GARMIN_POWER_XSD,
    GARMIN_TPX_V2_NS,
    GARMIN_TPX_V2_XSD,
    GPX_11_NS,
    GPX_11_XSD,
    PLACEWISE_NS,
    POINT_ELEMENTS,
)
from placewise.model._base import Model
from placewise.tracks import Track, TrackMeta

_NAN = math.nan
# xsd:decimal: digits with an optional point, no exponent, no nan/inf
_DECIMAL = re.compile(r"\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*")
_TIME = re.compile(
    r"\s*(\d{4})-(\d\d)-(\d\d)[Tt ](\d\d):(\d\d):(\d\d)(\.\d+)?\s*([Zz]|[+-]\d\d(?::?\d\d)?)?\s*"
)
_ACTIVITY_COMMENT = re.compile(r"\s*Activity\s*[=:]\s*(.*?)\s*", re.IGNORECASE)
_DATE = re.compile(r"\d{4}-\d\d-\d\d")
_CLOCK = re.compile(r"\d\d:\d\d:\d\d")
_EPOCH = dt.datetime(1970, 1, 1)
_EPOCH_ORDINAL = _EPOCH.toordinal()
_CHUNK = 8192  # points formatted at a time when writing, so memory tracks the output, not columns


@dataclass(frozen=True, slots=True)
class Waypoint(Model):
    name: str | None
    lat: float
    lon: float
    ele: float | None = None
    time: float | None = None  # UTC unix seconds
    desc: str | None = None


@dataclass(frozen=True)
class GpxFile:
    """One Track per `<trk>` (each `<trkseg>` a segment) and per `<rte>`; `track_hdop[i]` is the
    hdop of `tracks[i]` as a read-only array, or None when the file has none."""

    tracks: tuple[Track, ...] = ()
    routes: tuple[Track, ...] = ()
    waypoints: tuple[Waypoint, ...] = ()
    skipped: int = 0  # points and waypoints dropped for unusable coordinates
    track_hdop: tuple[np.ndarray | None, ...] = field(default=(), repr=False)
    route_hdop: tuple[np.ndarray | None, ...] = field(default=(), repr=False)


def read_gpx(source):
    """A GpxFile from a path, raw bytes, or a str holding either the XML or a path."""
    stream, name = _open(source)
    try:
        return _Reader(name).read(stream)
    except ET.ParseError as error:
        raise ValueError(f"not well-formed XML: {error}") from None
    finally:
        stream.close()


def _open(source):
    if isinstance(source, bytes | bytearray | memoryview):
        return io.BytesIO(source), "gpx"
    if isinstance(source, str) and source.lstrip().startswith("<"):
        return io.StringIO(source), "gpx"
    path = Path(source)
    return path.open("rb"), path.name


class _Builder:
    """Columns of one <trk> or <rte>, grown as points stream past; optional columns are created
    when first seen and NaN-padded, so absent fields cost nothing."""

    __slots__ = ("activity", "columns", "lat", "lon", "n", "name", "segment_start", "segments")

    def __init__(self):
        self.lat, self.lon = array("d"), array("d")
        self.columns = {}
        self.n = 0
        self.segments = []
        self.segment_start = 0
        self.name = self.activity = None

    def put(self, column, value):
        """Set `column` of the newest point unless it already has a value: standard elements
        come before <extensions>, so the first one wins."""
        arr = self.columns.get(column)
        i = self.n - 1
        if arr is not None and len(arr) == i:  # the usual case: every point carries the field
            arr.append(value)
            return
        if arr is None:
            arr = self.columns[column] = array("d")
        if len(arr) <= i:
            arr.extend(repeat(_NAN, i - len(arr)))
            arr.append(value)

    def end_segment(self):
        if self.n > self.segment_start:
            self.segments.append(self.segment_start)

    def build(self, meta, segmented):
        columns = {}
        for name, arr in self.columns.items():
            if len(arr) < self.n:
                arr.extend(repeat(_NAN, self.n - len(arr)))
            columns[name] = np.frombuffer(arr, dtype=np.float64)
        hdop = columns.pop("hdop", None)
        if hdop is not None:
            hdop = hdop.copy()
            hdop.flags.writeable = False
        time = columns.pop("time", None)
        if time is None:
            time = np.full(self.n, _NAN)
        segments = None
        if segmented and self.n:
            segments = self.segments if self.segments and self.segments[0] == 0 else [0, *self.segments]
        lat, lon = np.frombuffer(self.lat, dtype=np.float64), np.frombuffer(self.lon, dtype=np.float64)
        return Track(time, lat, lon, segments, meta, **columns), hdop


# end-event local names that need handling; everything else (the children of points, read in
# bulk when their point ends) costs one set lookup
_STRUCTURE = frozenset(("trkseg", "wpt", "name", "type", "keywords"))
_EXTENSIONS = object()


class _Reader:
    def __init__(self, source_name):
        self.source_name = source_name
        self.skipped = 0
        self.tracks, self.routes, self.waypoints = [], [], []
        self.file_name = self.keywords = self.comment_activity = self.creator = None
        # caches keyed by the raw "{namespace}local" tag; a file has only a handful of distinct tags
        self.local = {}
        self.point_child = {}
        self.extension_child = {}

    def _name(self, tag):
        local = self.local.get(tag)
        if local is None:
            local = self.local[tag] = tag[tag.rfind("}") + 1 :]
        return local

    def read(self, stream):
        stack, current, name, names = [], None, self._name, self.local
        for event, elem in ET.iterparse(stream, events=("start", "end", "comment")):
            if event == "end":
                stack.pop()
                local = names.get(elem.tag) or name(elem.tag)
                if local == "trkpt" or local == "rtept":
                    if current is not None:
                        self._point(elem, current)
                    del stack[-1][:]  # drop parsed points so memory stays flat on huge files
                    continue
                if local in _STRUCTURE:
                    parent = name(stack[-1].tag) if stack else None
                    if local == "trkseg":
                        if current is not None:
                            current.end_segment()
                    elif local == "wpt":
                        if parent == "gpx":
                            self._waypoint(elem)
                    else:
                        self._label(local, parent, current, elem.text)
                if len(stack) == 1:  # a finished top-level element: nothing in it is needed again
                    current = None
                    del stack[0][:]
            elif event == "start":
                stack.append(elem)
                depth = len(stack)
                if depth > 3:
                    continue
                local = name(elem.tag)
                if depth == 1:
                    if local != "gpx":
                        raise ValueError(f"not GPX: root element is <{local}>")
                    self.creator = elem.get("creator")
                elif depth == 2 and (local == "trk" or local == "rte"):
                    current = _Builder()
                    (self.tracks if local == "trk" else self.routes).append(current)
                elif local == "trkseg" and current is not None:
                    current.segment_start = current.n
            elif self.comment_activity is None:
                match = _ACTIVITY_COMMENT.fullmatch(elem.text or "")
                if match and match.group(1):
                    self.comment_activity = match.group(1)
        return self._result()

    def _label(self, local, parent, current, text):
        text = text.strip() if text else None
        if not text:
            return
        if parent in ("trk", "rte") and current is not None:
            if local == "name":
                current.name = text
            elif local == "type":
                current.activity = text
        elif parent == "metadata" or (parent == "gpx" and local in ("name", "keywords")):  # GPX 1.0
            if local == "name":
                self.file_name = text
            elif local == "keywords":
                self.keywords = text

    def _point_column(self, tag):
        local = self._name(tag)
        column = (
            _EXTENSIONS if local == "extensions" else "time" if local == "time" else POINT_ELEMENTS.get(local)
        )
        self.point_child[tag] = column
        return column

    def _extension_column(self, tag):
        column = self.extension_child[tag] = EXTENSION_ELEMENTS.get(self._name(tag))
        return column

    def _point(self, elem, builder):
        lat, lon = _coordinate(elem.get("lat"), 90.0), _coordinate(elem.get("lon"), 180.0)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            self.skipped += 1
            return
        builder.lat.append(lat)
        builder.lon.append(lon)
        builder.n += 1
        point_child, put = self.point_child, builder.put
        for child in elem:
            tag = child.tag
            column = point_child[tag] if tag in point_child else self._point_column(tag)
            if column is None:
                continue
            if column is _EXTENSIONS:
                extension_child = self.extension_child
                for sub in child.iter():
                    tag = sub.tag
                    column = extension_child[tag] if tag in extension_child else self._extension_column(tag)
                    if column is not None and (value := _number(sub.text)) is not None:
                        put(column, value)
            elif column == "time":
                put("time", _parse_time(child.text))
            elif (value := _number(child.text)) is not None:
                put(column, value)

    def _waypoint(self, elem):
        lat, lon = _coordinate(elem.get("lat"), 90.0), _coordinate(elem.get("lon"), 180.0)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            self.skipped += 1
            return
        values = {"name": None, "ele": None, "time": None, "desc": None}
        for child in elem:
            local = self._name(child.tag)
            if local == "ele":
                values["ele"] = _number(child.text)
            elif local == "time":
                time = _parse_time(child.text)
                values["time"] = None if math.isnan(time) else time
            elif local in ("name", "desc") and child.text and child.text.strip():
                values[local] = child.text.strip()
        self.waypoints.append(
            Waypoint(values["name"], lat, lon, values["ele"], values["time"], values["desc"])
        )

    def _result(self):
        def build(builders, segmented):
            tracks, hdops = [], []
            for b in builders:
                activity = b.activity or self.comment_activity or self.keywords
                meta = TrackMeta(b.name or self.file_name, activity, self.creator, self.source_name)
                track, hdop = b.build(meta, segmented)
                tracks.append(track)
                hdops.append(hdop)
            return tuple(tracks), tuple(hdops)

        tracks, track_hdop = build(self.tracks, True)
        routes, route_hdop = build(self.routes, False)
        return GpxFile(tracks, routes, tuple(self.waypoints), self.skipped, track_hdop, route_hdop)


def _coordinate(text, limit):
    if text is None or not _DECIMAL.fullmatch(text):
        return None
    value = float(text)
    return value if -limit <= value <= limit else None


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=4096)
def _day_seconds(year, month, day):
    return (dt.date(year, month, day).toordinal() - _EPOCH_ORDINAL) * 86400


@lru_cache(maxsize=4096)
def _date_seconds(date):
    """Unix seconds at the start of a YYYY-MM-DD day, or None."""
    if not _DATE.fullmatch(date):
        return None
    try:
        return _day_seconds(int(date[:4]), int(date[5:7]), int(date[8:10]))
    except ValueError:
        return None


def _parse_time(text):
    # fast path for the overwhelmingly common "2024-05-01T12:00:00Z"
    if text is not None and len(text) == 20 and text[19] == "Z" and text[10] == "T":
        day = _date_seconds(text[:10])
        clock = text[11:19]
        if day is not None and _CLOCK.fullmatch(clock):
            return float(day + int(clock[:2]) * 3600 + int(clock[3:5]) * 60 + int(clock[6:]))
    match = _TIME.fullmatch(text) if text else None
    if match is None:
        return _NAN
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    try:
        seconds = _day_seconds(int(year), int(month), int(day))
    except ValueError:  # 2024-13-45 and the like
        return _NAN
    # a leap second (:60) simply rolls into the next minute
    seconds += int(hour) * 3600 + int(minute) * 60 + int(second)
    if zone and zone.upper() != "Z":
        digits = zone[1:].replace(":", "")
        offset = int(digits[:2]) * 3600 + int(digits[2:4] or 0) * 60
        seconds += -offset if zone[0] == "+" else offset
    return seconds + float(fraction) if fraction else float(seconds)


def write_gpx(tracks, path_or_none, waypoints=(), creator="placewise"):
    """GPX 1.1 text for a Track or iterable of Tracks (and Waypoints); also written to the path
    when one is given. NaN values (time included) are left out of the file."""
    if isinstance(tracks, Track):
        tracks = (tracks,)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<gpx version="1.1" creator={_attribute(creator)} xmlns="{GPX_11_NS}"'
        f' xmlns:gpxtpx="{GARMIN_TPX_V2_NS}" xmlns:gpxpx="{GARMIN_POWER_NS}"'
        f' xmlns:placewise="{PLACEWISE_NS}"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        f' xsi:schemaLocation="{GPX_11_NS} {GPX_11_XSD} {GARMIN_TPX_V2_NS} {GARMIN_TPX_V2_XSD}'
        f' {GARMIN_POWER_NS} {GARMIN_POWER_XSD}">\n'
    ]
    for w in waypoints:
        parts.append(f'<wpt lat="{_decimal(w.lat)}" lon="{_decimal(w.lon)}">')
        if w.ele is not None and math.isfinite(w.ele):
            parts.append(f"<ele>{_decimal(w.ele)}</ele>")
        if w.time is not None and math.isfinite(w.time):
            parts.append(f"<time>{_format_time(w.time)}</time>")
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
    def strings(column):
        fmt = _format_time if column == "time" else _integer if column in _INTEGER_COLUMNS else _decimal
        return [None if v != v else fmt(v) for v in getattr(track, column)[rows].tolist()]  # v != v: NaN

    lat = [_decimal(v) for v in track.lat[rows].tolist()]
    lon = [_decimal(v) for v in track.lon[rows].tolist()]
    plain = [(f"<{e}>", f"</{e}>", strings(c)) for c, e in plain]
    tpx = [(f"<gpxtpx:{e}>", f"</gpxtpx:{e}>", strings(c)) for c, e in tpx]
    power = strings("power") if "power" in present else None
    accuracy = strings("accuracy") if "accuracy" in present else None
    out = []
    for i in range(len(lat)):
        point = [f'<trkpt lat="{lat[i]}" lon="{lon[i]}">']
        point += [f"{a}{s[i]}{b}" for a, b, s in plain if s[i] is not None]
        extensions = [f"{a}{s[i]}{b}" for a, b, s in tpx if s[i] is not None]
        if extensions:
            extensions = ["<gpxtpx:TrackPointExtension>", *extensions, "</gpxtpx:TrackPointExtension>"]
        if power and power[i] is not None:
            extensions.append(f"<gpxpx:PowerInWatts>{power[i]}</gpxpx:PowerInWatts>")
        if accuracy and accuracy[i] is not None:
            extensions.append(f"<placewise:accuracy>{accuracy[i]}</placewise:accuracy>")
        if extensions:
            point.append(f"<extensions>{''.join(extensions)}</extensions>")
        point.append("</trkpt>\n")
        out.append("".join(point))
    return "".join(out)


def _attribute(text):
    return f'"{escape(text, {chr(34): "&quot;"})}"'


def _decimal(value):
    # repr is the shortest string that reads back to the same float; xsd:decimal forbids its exponent form
    text = repr(value)
    if "e" in text:
        text = np.format_float_positional(value, trim="-")
    return text[:-2] if text.endswith(".0") else text


def _integer(value):
    return str(round(value))


def _format_time(value):
    whole = math.floor(value)
    micro = round((value - whole) * 1e6)
    if micro == 1_000_000:
        whole, micro = whole + 1, 0
    stamp = (_EPOCH + dt.timedelta(seconds=whole)).isoformat()
    if micro:
        stamp += f".{micro:06d}".rstrip("0")
    return stamp + "Z"
