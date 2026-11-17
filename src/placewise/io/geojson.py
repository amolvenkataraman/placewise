"""GeoJSON polygons (RFC 7946) into Features. GeoJSON orders positions (lon, lat); placewise flips them."""

import json
from pathlib import Path

from placewise.model import Feature, Outline

_GEOMETRY_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
}


def read_geojson(source):
    """Polygon and MultiPolygon features from a path, a JSON string's parsed dict, a Feature,
    a FeatureCollection or a bare geometry. Other geometry types are skipped."""
    data = source if isinstance(source, dict) else json.loads(Path(source).read_text(encoding="utf-8"))
    kind = data.get("type")
    if kind == "FeatureCollection":
        items = data.get("features", [])
    elif kind == "Feature":
        items = [data]
    elif kind in _GEOMETRY_TYPES:
        items = [{"type": "Feature", "geometry": data}]
    else:
        raise ValueError(f"not GeoJSON: type {kind!r}")
    features = []
    for item in items:
        outlines = _outlines(item.get("geometry") or {})
        if outlines:
            fid = item.get("id")
            features.append(
                Feature(outlines, dict(item.get("properties") or {}), None if fid is None else str(fid))
            )
    return features


def _outlines(geometry):
    kind = geometry.get("type")
    if kind == "Polygon":
        polygons = [geometry["coordinates"]]
    elif kind == "MultiPolygon":
        polygons = geometry["coordinates"]
    elif kind == "GeometryCollection":
        return tuple(o for g in geometry.get("geometries", []) for o in _outlines(g))
    else:
        return ()
    return tuple(
        Outline(tuple(tuple((float(pos[1]), float(pos[0])) for pos in ring) for ring in polygon))
        for polygon in polygons
    )
