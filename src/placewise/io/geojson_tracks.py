"""GeoJSON tracks: LineString and MultiLineString features, with per-point times.

Times come from the conventions in use: a `coordTimes` property (togeojson, Strava and Mapbox
exports), `coordinateProperties.times` (newer togeojson) or a fourth coordinate value holding unix
time; without any, times are NaN. GeoJSON orders positions (lon, lat[, ele]); placewise flips them.
"""

import json
import math
from itertools import pairwise

import numpy as np

from placewise.constants import track_files
from placewise.tracks import OPTIONAL_COLUMNS, TrackMeta

from ._track_common import build_track, format_iso_time, new_points, parse_iso_time, read_source, source_name

_GEOMETRY_TYPES = ("Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon")
_PER_POINT = {name: name for name in OPTIONAL_COLUMNS} | track_files.GEOJSON_COORDINATE_PROPERTY_COLUMNS


def read_geojson_tracks(source):
    """Tracks from a GeoJSON path, bytes, file object or parsed dict (FeatureCollection, Feature or
    bare geometry): one per LineString / MultiLineString feature, whose parts become segments."""
    data = source if isinstance(source, dict) else json.loads(read_source(source).decode("utf-8-sig"))
    kind = data.get("type")
    if kind == "FeatureCollection":
        items = data.get("features") or []
    elif kind == "Feature":
        items = [data]
    elif kind in _GEOMETRY_TYPES or kind == "GeometryCollection":
        items = [{"type": "Feature", "geometry": data}]
    else:
        raise ValueError(f"not GeoJSON: type {kind!r}")
    origin = None if isinstance(source, dict) else source_name(source, "geojson")
    tracks = []
    for item in items:
        track = _read_feature(item, origin)
        if track is not None:
            tracks.append(track)
    return tracks


def _read_feature(feature, origin):
    geometry = feature.get("geometry") or {}
    if geometry.get("type") == "LineString":
        parts = [geometry.get("coordinates") or []]
    elif geometry.get("type") == "MultiLineString":
        parts = geometry.get("coordinates") or []
    else:
        return None
    parts = [p for p in parts if p]
    if not parts:
        return None
    props = feature.get("properties") or {}
    per_point = props.get("coordinateProperties") or {}
    times = _per_part(_first(props, per_point, track_files.GEOJSON_TIME_KEYS), parts)
    extras = {}
    for key, values in per_point.items():
        column = _PER_POINT.get(key)
        if column and column != "time" and column not in extras and (shaped := _per_part(values, parts)):
            extras[column] = shaped
    points = new_points(OPTIONAL_COLUMNS)
    segments = []
    for p, part in enumerate(parts):
        segments.append(len(points["time"]))
        for i, position in enumerate(part):
            points["lon"].append(float(position[0]))
            points["lat"].append(float(position[1]))
            points["ele"].append(_number(position[2]) if len(position) > 2 else math.nan)
            if times is not None:
                points["time"].append(_time(times[p][i]))
            else:
                points["time"].append(_time(position[3]) if len(position) > 3 else math.nan)
            for column in OPTIONAL_COLUMNS:
                if column != "ele":
                    points[column].append(_number(extras[column][p][i]) if column in extras else math.nan)
    activities = (props[k] for k in track_files.GEOJSON_ACTIVITY_KEYS if isinstance(props.get(k), str))
    meta = TrackMeta(
        name=_string(props.get("name")),
        activity=next(activities, None),
        device=_string(props.get("device")),
        source=origin,
    )
    return build_track(points, segments, meta)


def _first(props, per_point, keys):
    for container in (props, per_point):
        for key in keys:
            if container.get(key) is not None:
                return container[key]
    return None


def _per_part(values, parts):
    """Per-point values split like the geometry's parts, or None when they don't line up.

    Writers nest them per part for a MultiLineString, but some flatten them, so both are accepted."""
    if not isinstance(values, list):
        return None
    sizes = [len(p) for p in parts]
    if len(values) == len(parts) and all(isinstance(v, list) for v in values):
        return values if [len(v) for v in values] == sizes else None
    if len(values) == sum(sizes):
        bounds = np.cumsum([0, *sizes])
        return [values[a:b] for a, b in pairwise(bounds)]
    return None


def _string(value):
    return value if isinstance(value, str) else None


def _number(value):
    return math.nan if value is None else float(value)


def _time(value):
    if value is None:
        return math.nan
    if isinstance(value, str):
        return parse_iso_time(value)
    value = float(value)
    return value / 1000 if abs(value) > track_files.UNIX_MILLISECONDS_ABOVE else value


def write_geojson_track(track):
    """A GeoJSON Feature for a Track: a LineString, or a MultiLineString when it has several segments.

    Times go to `coordTimes` (ISO 8601, null where unknown), other columns to `coordinateProperties`
    under their placewise names, elevation to the third coordinate."""
    bounds = list(pairwise((*track.segments, len(track))))
    ele = track.ele
    coordinates = [
        [
            [float(track.lon[i]), float(track.lat[i])]
            + ([] if ele is None or math.isnan(ele[i]) else [float(ele[i])])
            for i in range(a, b)
        ]
        for a, b in bounds
    ]
    times = [[format_iso_time(float(t)) for t in track.time[a:b]] for a, b in bounds]
    per_point = {
        name: [[None if math.isnan(v) else float(v) for v in getattr(track, name)[a:b]] for a, b in bounds]
        for name in track.columns
        if name in OPTIONAL_COLUMNS and name != "ele"
    }
    multi = len(bounds) > 1
    meta = track.meta
    named = (("name", meta.name), ("activity", meta.activity), ("device", meta.device))
    properties = {k: v for k, v in named if v is not None}
    properties["coordTimes"] = times if multi else (times[0] if times else [])
    if per_point:
        properties["coordinateProperties"] = {k: v if multi else v[0] for k, v in per_point.items()}
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "MultiLineString" if multi else "LineString",
            "coordinates": coordinates if multi else (coordinates[0] if coordinates else []),
        },
    }
