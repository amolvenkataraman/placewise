"""Garmin Training Center XML (TCX) tracks in and out.

Each Activity (or Course) becomes one Track; every Lap and every Track element inside a Lap starts a
segment. Elements are matched by local name, so files that use another namespace prefix, the older
v1 namespace or none at all still read.
"""

import math
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path

import numpy as np

from placewise.constants import tcx
from placewise.geo import haversine
from placewise.tracks import TrackMeta

from ._track_common import (
    build_track,
    format_iso_time,
    iter_xml,
    local_name,
    new_points,
    parse_iso_time,
    read_source,
    source_name,
    to_float,
    warn_skipped,
    xml_child,
    xml_text,
)

_COLUMNS = ("ele", "speed", "hr", "cadence", "power")


_CONTAINERS = ("Activity", "Course")


class _Container:
    """Points of one Activity or Course, gathered as its Trackpoints stream past."""

    __slots__ = ("element", "kind", "points", "segments", "skipped", "track_starts")

    def __init__(self, element, kind):
        self.element, self.kind = element, kind
        self.points = new_points(_COLUMNS)
        self.segments, self.skipped = [], 0
        self.track_starts = []  # point count at the start of each open Track


def read_tcx(source):
    """Tracks from a TCX path, bytes or file object: one per Activity and per Course.

    Trackpoints without a Position (heart rate logged before the GPS fix, indoor sessions) are
    skipped; a TrackReadWarning reports how many. The file is streamed: each Trackpoint is read
    when it ends and then dropped."""
    data = read_source(source)
    origin = source_name(source, "tcx")
    tracks, skipped = [], 0
    stack, containers, root = [], [], None
    for event, element in iter_xml(data):
        if root is None:
            root = local_name(element.tag)
        if root != tcx.ROOT_ELEMENT:  # read on: malformed XML is reported before a wrong root
            element.clear()
            continue
        if event == "start":
            kind = local_name(element.tag)
            stack.append(element)
            if kind in _CONTAINERS:
                containers.append(_Container(element, kind))
            elif kind == "Track":
                for c in containers:
                    c.track_starts.append(len(c.points["time"]))
            continue
        stack.pop()
        kind = local_name(element.tag)
        if kind == "Trackpoint":
            if containers and stack and local_name(stack[-1].tag) == "Track":
                for c in containers:
                    if not _read_trackpoint(element, c.points):
                        c.skipped += 1
                del stack[-1][:]  # read: drop it, so memory stays flat on huge files
        elif kind == "Track":
            for c in containers:
                start = c.track_starts.pop()
                if len(c.points["time"]) > start:
                    c.segments.append(start)
        elif kind in _CONTAINERS and containers and containers[-1].element is element:
            container = containers.pop()
            track = _finish(container, origin)
            skipped += container.skipped
            if track is not None:
                tracks.append(track)
            if stack:
                stack[-1].remove(element)
    if root != tcx.ROOT_ELEMENT:
        raise ValueError(f"not TCX: root element is <{root}>")
    warn_skipped(skipped, "trackpoint(s)", "no Position", "TCX")
    return tracks


def _finish(container, origin):
    points = container.points
    if not points["time"]:
        return None
    element = container.element
    if container.kind == "Activity":
        name, activity = None, element.get("Sport")
    else:
        name, activity = xml_text(xml_child(element, "Name")), None
    device = xml_text(xml_child(xml_child(element, "Creator"), "Name"))
    meta = TrackMeta(name=name, activity=activity, device=device, source=origin)
    return build_track(points, container.segments, meta)


def _read_trackpoint(tp, points):
    child = _children(tp)
    position = _children(child.get("Position"))
    lat = to_float(xml_text(position.get("LatitudeDegrees")))
    lon = to_float(xml_text(position.get("LongitudeDegrees")))
    if math.isnan(lat) or math.isnan(lon):
        return False
    time_text = xml_text(child.get("Time"))
    points["time"].append(parse_iso_time(time_text) if time_text else math.nan)
    points["lat"].append(lat)
    points["lon"].append(lon)
    points["ele"].append(to_float(xml_text(child.get("AltitudeMeters"))))
    points["hr"].append(to_float(xml_text(_children(child.get("HeartRateBpm")).get("Value"))))
    tpx = _children(_children(child.get("Extensions")).get("TPX"))
    cadence = to_float(xml_text(child.get("Cadence")))
    if math.isnan(cadence):  # runners' footpods report steps per minute in the extension instead
        cadence = to_float(xml_text(tpx.get("RunCadence")))
    points["cadence"].append(cadence)
    points["speed"].append(to_float(xml_text(tpx.get("Speed"))))
    points["power"].append(to_float(xml_text(tpx.get("Watts"))))
    return True


def _children(element):
    """The first child of each local name (as xml_child finds it); none for no element."""
    if element is None:
        return {}
    found = {}
    for c in element:
        found.setdefault(local_name(c.tag), c)
    return found


def write_tcx(track, path=None):
    """TCX text for a Track (one Activity, one Lap per segment); also written to `path` if given.

    TCX requires a time on every Trackpoint, so a track with NaN times is refused."""
    if len(track) and not np.all(np.isfinite(track.time)):
        raise ValueError("TCX needs a time for every point; this track has missing (NaN) times")
    # namespaces are written as plain xmlns attributes and prefixed tag names: ET.register_namespace
    # changes process-wide state and refuses Garmin's own "ns3" prefix
    root = ET.Element(
        "TrainingCenterDatabase",
        {
            "xmlns": tcx.TCX_NS,
            "xmlns:ns3": tcx.ACTIVITY_EXTENSION_NS,
            "xmlns:xsi": tcx.XSI_NS,
            "xsi:schemaLocation": tcx.SCHEMA_LOCATION,
        },
    )
    activities = ET.SubElement(root, "Activities")
    sport = track.meta.activity if track.meta.activity in tcx.SPORTS else tcx.DEFAULT_SPORT
    activity = ET.SubElement(activities, "Activity", Sport=sport)
    ET.SubElement(activity, "Id").text = format_iso_time(track.time[0] if len(track) else 0.0)
    for start, end in pairwise((*track.segments, len(track))):
        _write_lap(activity, track, start, end)
    if track.meta.device:
        creator = ET.SubElement(activity, "Creator")
        creator.set("xsi:type", "Device_t")
        ET.SubElement(creator, "Name").text = track.meta.device
    ET.indent(root)
    text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    if path is not None:
        Path(path).write_text(text, encoding="utf-8")
    return text


def _write_lap(activity, track, start, end):
    lat, lon, time = track.lat[start:end], track.lon[start:end], track.time[start:end]
    metres = float(np.sum(haversine(lat[:-1], lon[:-1], lat[1:], lon[1:]))) * 1000 if end - start > 1 else 0.0
    lap = ET.SubElement(activity, "Lap", StartTime=format_iso_time(time[0]))
    ET.SubElement(lap, "TotalTimeSeconds").text = _num(time[-1] - time[0])
    ET.SubElement(lap, "DistanceMeters").text = _num(round(metres, 1))
    ET.SubElement(lap, "Calories").text = "0"
    ET.SubElement(lap, "Intensity").text = "Active"
    ET.SubElement(lap, "TriggerMethod").text = "Manual"
    track_el = ET.SubElement(lap, "Track")
    for i in range(start, end):
        tp = ET.SubElement(track_el, "Trackpoint")
        ET.SubElement(tp, "Time").text = format_iso_time(track.time[i])
        position = ET.SubElement(tp, "Position")
        ET.SubElement(position, "LatitudeDegrees").text = _num(track.lat[i])
        ET.SubElement(position, "LongitudeDegrees").text = _num(track.lon[i])
        if (ele := _value(track.ele, i)) is not None:
            ET.SubElement(tp, "AltitudeMeters").text = _num(ele)
        if (hr := _value(track.hr, i)) is not None:
            low, high = tcx.HEART_RATE_RANGE
            ET.SubElement(ET.SubElement(tp, "HeartRateBpm"), "Value").text = str(
                min(max(round(hr), low), high)
            )
        if (cadence := _value(track.cadence, i)) is not None:
            low, high = tcx.CADENCE_RANGE
            ET.SubElement(tp, "Cadence").text = str(min(max(round(cadence), low), high))
        speed, power = _value(track.speed, i), _value(track.power, i)
        if speed is not None or power is not None:
            tpx = ET.SubElement(ET.SubElement(tp, "Extensions"), "ns3:TPX")
            if speed is not None:
                ET.SubElement(tpx, "ns3:Speed").text = _num(speed)
            if power is not None:
                ET.SubElement(tpx, "ns3:Watts").text = str(round(power))


def _value(column, i):
    if column is None or math.isnan(column[i]):
        return None
    return float(column[i])


def _num(value):
    # repr is the shortest text that reads back to the same float
    value = float(value)
    return str(int(value)) if value.is_integer() else repr(value)
