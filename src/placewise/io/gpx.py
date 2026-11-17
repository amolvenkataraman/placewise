"""GPX 1.0 / 1.1 tracks, routes and waypoints in and out, streamed through expat with no element tree.

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
_DECIMAL_CHARS = "0123456789.+-"
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
    reader = _Reader(name)
    parser = ET.XMLParser(target=reader)
    try:
        while chunk := stream.read(_READ_BYTES):
            parser.feed(chunk)
        parser.close()
    except ET.ParseError as error:
        raise ValueError(f"not well-formed XML: {error}") from None
    finally:
        stream.close()
    return reader.result()


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


# local names that mean something outside points and waypoints; everything inside a point or
# waypoint is collected and read when it ends
_LABELS = frozenset(("name", "type", "keywords"))
_LABEL_PARENTS = frozenset(("trk", "rte", "metadata", "gpx"))
_EXTENSIONS = object()
_READ_BYTES = 1 << 20


class _Reader:
    """An ElementTree parser target: expat calls start / end / data / comment as it reads, and no
    element tree is built. A point or waypoint is collected as a pre-order list of its descendants'
    [tag, text, depth below it], with text meaning what Element.text does (the text before the
    first child), and read when it ends."""

    def __init__(self, source_name):
        self.source_name = source_name
        self.skipped = 0
        self.tracks, self.routes, self.waypoints = [], [], []
        self.file_name = self.keywords = self.comment_activity = self.creator = None
        self.stack = []  # local names of the open elements
        self.current = None  # the _Builder of the open <trk> or <rte>
        self.capture = None  # descendants of the open point or waypoint, while one is open
        self.capture_attrib = None
        self.inner = 0  # depth below the open point or waypoint
        self.open_entry = None  # the [tag, text, depth] still taking text: no child seen yet
        self.label = None  # (depth, entry) of an open <name>, <type> or <keywords> that counts
        # caches keyed by the raw "{namespace}local" tag; a file has only a handful of distinct tags
        self.local = {}
        self.point_child = {}
        self.extension_child = {}

    def _name(self, tag):
        local = self.local.get(tag)
        if local is None:
            local = self.local[tag] = tag[tag.rfind("}") + 1 :]
        return local

    def start(self, tag, attrib):
        if self.capture is not None:  # the hot path: the children of points
            self.inner += 1
            self.open_entry = entry = [tag, None, self.inner]
            self.capture.append(entry)
            return
        stack = self.stack
        depth = len(stack) + 1
        local = self.local.get(tag) or self._name(tag)
        parent = stack[-1] if stack else None
        stack.append(local)
        self.open_entry = None
        if depth == 1:
            if local != "gpx":
                raise ValueError(f"not GPX: root element is <{local}>")
            self.creator = attrib.get("creator")
        elif depth == 2 and (local == "trk" or local == "rte"):
            self.current = _Builder()
            (self.tracks if local == "trk" else self.routes).append(self.current)
        elif depth == 3 and local == "trkseg" and self.current is not None:
            self.current.segment_start = self.current.n
        if local == "trkpt" or local == "rtept":
            if self.current is not None:
                self.capture, self.capture_attrib = [], attrib
        elif local == "wpt":
            if parent == "gpx":
                self.capture, self.capture_attrib = [], attrib
        elif local in _LABELS and parent in _LABEL_PARENTS:
            self.open_entry = entry = [tag, None, 0]
            self.label = (depth, entry)

    def data(self, text):
        entry = self.open_entry
        if entry is not None:
            entry[1] = text if entry[1] is None else entry[1] + text

    def end(self, tag):
        self.open_entry = None
        if self.inner:
            self.inner -= 1
            return
        stack = self.stack
        depth = len(stack)
        local = stack.pop()
        if self.capture is not None:
            entries, self.capture = self.capture, None
            if local == "wpt":
                self._waypoint(self.capture_attrib, entries)
            else:
                self._point(self.capture_attrib, entries, self.current)
                return  # a point never closes its <trk> or <rte>
        elif local == "trkseg":
            if self.current is not None:
                self.current.end_segment()
        elif self.label is not None and self.label[0] == depth:
            _, entry = self.label
            self.label = None
            self._label(local, stack[-1], self.current, entry[1])
        if depth == 2:  # a finished top-level element
            self.current = None

    def comment(self, text):
        if self.comment_activity is None:
            match = _ACTIVITY_COMMENT.fullmatch(text or "")
            if match and match.group(1):
                self.comment_activity = match.group(1)

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

    def _point(self, attrib, entries, builder):
        lat, lon = _coordinate(attrib.get("lat"), 90.0), _coordinate(attrib.get("lon"), 180.0)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            self.skipped += 1
            return
        builder.lat.append(lat)
        builder.lon.append(lon)
        builder.n += 1
        point_child, extension_child, put = self.point_child, self.extension_child, builder.put
        get, last = builder.columns.get, builder.n - 1
        in_extensions = False
        for tag, text, depth in entries:
            if depth == 1:  # a child of the point
                column = point_child[tag] if tag in point_child else self._point_column(tag)
                in_extensions = column is _EXTENSIONS
                if column is None:
                    continue
                if column == "time":
                    value = _parse_time(text)
                elif in_extensions:
                    column = extension_child[tag] if tag in extension_child else self._extension_column(tag)
                    if column is None or (value := _number(text)) is None:
                        continue
                elif (value := _number(text)) is None:
                    continue
            elif in_extensions:  # everything inside <extensions>, matched by local name
                column = extension_child[tag] if tag in extension_child else self._extension_column(tag)
                if column is None or (value := _number(text)) is None:
                    continue
            else:
                continue
            arr = get(column)
            if arr is not None and len(arr) == last:  # the usual case: every point has the field
                arr.append(value)
            else:
                put(column, value)

    def _waypoint(self, attrib, entries):
        lat, lon = _coordinate(attrib.get("lat"), 90.0), _coordinate(attrib.get("lon"), 180.0)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            self.skipped += 1
            return
        values = {"name": None, "ele": None, "time": None, "desc": None}
        for tag, text, depth in entries:
            if depth != 1:
                continue
            local = self._name(tag)
            if local == "ele":
                values["ele"] = _number(text)
            elif local == "time":
                time = _parse_time(text)
                values["time"] = None if math.isnan(time) else time
            elif local in ("name", "desc") and text and text.strip():
                values[local] = text.strip()
        self.waypoints.append(
            Waypoint(values["name"], lat, lon, values["ele"], values["time"], values["desc"])
        )

    def result(self):

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
    if text is None:
        return None
    if text.strip(_DECIMAL_CHARS):  # anything beyond plain ASCII digits, point and sign
        if not _DECIMAL.fullmatch(text):
            return None
        value = float(text)
    else:  # over these characters float() takes exactly what xsd:decimal does
        try:
            value = float(text)
        except ValueError:
            return None
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
            parts.append(f"<name>{_escape(w.name)}</name>")
        if w.desc:
            parts.append(f"<desc>{_escape(w.desc)}</desc>")
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
        parts.append(f"<name>{_escape(track.meta.name)}</name>")
    if track.meta.activity:
        parts.append(f"<type>{_escape(track.meta.activity)}</type>")
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
    """_decimal of each value, None for NaN."""
    texts = [t[:-2] if t.endswith(".0") else t for t in map(repr, values.tolist())]
    for k in [k for k, t in enumerate(texts) if "e" in t]:
        texts[k] = _decimal(float(values[k]))
    return _nan_to_none(texts, values)


def _integer_strings(values):
    """_integer of each value, None for NaN."""
    finite = values[~np.isnan(values)]
    if len(finite) and not np.all(np.abs(finite) < 2**52):  # inf, or past exact integers
        return [None if v != v else _integer(v) for v in values.tolist()]
    # np.rint rounds half to even, as round() does
    texts = list(map(str, np.rint(np.nan_to_num(values)).astype(np.int64).tolist()))
    return _nan_to_none(texts, values)


_LAST_ISO_SECOND = 253402300799  # 9999-12-31T23:59:59, the last second datetime can print


def _time_strings(values):
    """_format_time of each value, None for NaN."""
    finite = values[~np.isnan(values)]
    if len(finite) and not (np.all(finite >= 0) and np.all(finite <= _LAST_ISO_SECOND)):
        return [None if v != v else _format_time(v) for v in values.tolist()]
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


def _escape(text, entities=None):
    """xml.sax.saxutils.escape, without importing xml.sax (which pulls in urllib, http and ssl)."""
    text = text.replace("&", "&amp;").replace(">", "&gt;").replace("<", "&lt;")
    for key, value in (entities or {}).items():
        text = text.replace(key, value)
    return text


def _attribute(text):
    return f'"{_escape(text, {chr(34): "&quot;"})}"'


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
