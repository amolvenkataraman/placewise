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

_COLUMNS = ("ele", "speed", "hr", "cadence", "power")


def read_tcx(source):
    """Tracks from a TCX path, bytes or file object: one per Activity and per Course.

    Trackpoints without a Position (heart rate logged before the GPS fix, indoor sessions) are
    skipped; a TrackReadWarning reports how many."""
    root = parse_xml(read_source(source))
    if local_name(root.tag) != tcx.ROOT_ELEMENT:
        raise ValueError(f"not TCX: root element is <{local_name(root.tag)}>")
    origin = source_name(source, "tcx")
    tracks, skipped = [], 0
    for element in root.iter():
        kind = local_name(element.tag)
        if kind not in ("Activity", "Course"):
            continue
        track, missing = _read_container(element, kind, origin)
        skipped += missing
        if track is not None:
            tracks.append(track)
    warn_skipped(skipped, "trackpoint(s)", "no Position", "TCX")
    return tracks


def _read_container(container, kind, origin):
    points = new_points(_COLUMNS)
    segments, skipped = [], 0
    # a Course keeps its Track beside its Laps, an Activity inside each Lap; both are just Track elements
    for track_el in (e for e in container.iter() if local_name(e.tag) == "Track"):
        start = len(points["time"])
        for tp in xml_children(track_el, "Trackpoint"):
            if not _read_trackpoint(tp, points):
                skipped += 1
        if len(points["time"]) > start:
            segments.append(start)
    if not points["time"]:
        return None, skipped
    if kind == "Activity":
        name, activity = None, container.get("Sport")
    else:
        name, activity = xml_text(xml_child(container, "Name")), None
    device = xml_text(xml_child(xml_child(container, "Creator"), "Name"))
    meta = TrackMeta(name=name, activity=activity, device=device, source=origin)
    return build_track(points, segments, meta), skipped


def _read_trackpoint(tp, points):
    position = xml_child(tp, "Position")
    lat = to_float(xml_text(xml_child(position, "LatitudeDegrees")))
    lon = to_float(xml_text(xml_child(position, "LongitudeDegrees")))
    if math.isnan(lat) or math.isnan(lon):
        return False
    time_text = xml_text(xml_child(tp, "Time"))
    points["time"].append(parse_iso_time(time_text) if time_text else math.nan)
    points["lat"].append(lat)
    points["lon"].append(lon)
    points["ele"].append(to_float(xml_text(xml_child(tp, "AltitudeMeters"))))
    points["hr"].append(to_float(xml_text(xml_child(xml_child(tp, "HeartRateBpm"), "Value"))))
    tpx = xml_child(xml_child(tp, "Extensions"), "TPX")
    cadence = to_float(xml_text(xml_child(tp, "Cadence")))
    if math.isnan(cadence):  # runners' footpods report steps per minute in the extension instead
        cadence = to_float(xml_text(xml_child(tpx, "RunCadence")))
    points["cadence"].append(cadence)
    points["speed"].append(to_float(xml_text(xml_child(tpx, "Speed"))))
    points["power"].append(to_float(xml_text(xml_child(tpx, "Watts"))))
    return True


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
