"""Reading GPX: an expat parser target that streams points into columns, building no element tree
(the rules are in the package's docstring)."""

import io
import math
import xml.etree.ElementTree as ET
from array import array
from dataclasses import dataclass, field
from itertools import repeat
from pathlib import Path

import numpy as np

from placewise.constants.gpx import EXTENSION_ELEMENTS, POINT_ELEMENTS
from placewise.model._base import Model
from placewise.tracks import Track, TrackMeta

from .values import ACTIVITY_COMMENT, coordinate, number, parse_time

_NAN = math.nan


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
            match = ACTIVITY_COMMENT.fullmatch(text or "")
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
        lat, lon = coordinate(attrib.get("lat"), 90.0), coordinate(attrib.get("lon"), 180.0)
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
                    value = parse_time(text)
                elif in_extensions:
                    column = extension_child[tag] if tag in extension_child else self._extension_column(tag)
                    if column is None or (value := number(text)) is None:
                        continue
                elif (value := number(text)) is None:
                    continue
            elif in_extensions:  # everything inside <extensions>, matched by local name
                column = extension_child[tag] if tag in extension_child else self._extension_column(tag)
                if column is None or (value := number(text)) is None:
                    continue
            else:
                continue
            arr = get(column)
            if arr is not None and len(arr) == last:  # the usual case: every point has the field
                arr.append(value)
            else:
                put(column, value)

    def _waypoint(self, attrib, entries):
        lat, lon = coordinate(attrib.get("lat"), 90.0), coordinate(attrib.get("lon"), 180.0)
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            self.skipped += 1
            return
        values = {"name": None, "ele": None, "time": None, "desc": None}
        for tag, text, depth in entries:
            if depth != 1:
                continue
            local = self._name(tag)
            if local == "ele":
                values["ele"] = number(text)
            elif local == "time":
                time = parse_time(text)
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
