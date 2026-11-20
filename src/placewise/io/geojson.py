"""GeoJSON (RFC 7946) polygons in and out. GeoJSON orders positions (lon, lat); placewise flips them.

In: `read_geojson` makes Features of Polygon and MultiPolygon features.
Out: `outline_geometry` turns an Outline (even-odd rings, as packs and Entities hold them) into a
Polygon or MultiPolygon with each hole under the ring that holds it, outer rings counter-clockwise
and holes clockwise, optionally simplified to within `simplify_m` metres; `entity_feature` makes
a Feature of a search Entity (its outline, else its point); `to_geojson` and `write_geojson` a
FeatureCollection of Entities, Outlines or Features.
"""

import json
from pathlib import Path

import numpy as np

from placewise.geo import lines, shapes
from placewise.model import Entity, Feature, Outline

COORD_DECIMALS = 7  # 1 cm; packs store coordinates as 1e-7 degree integers

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


def outline_geometry(outline, simplify_m=None):
    """The GeoJSON geometry dict of an Outline: a Polygon, or a MultiPolygon when its rings make
    several polygons. simplify_m: drop vertices while every ring stays within that many metres of
    the original (Douglas-Peucker); rings smaller than that are left out (a polygon's holes with
    it), but never every ring: the biggest polygon then stays as it was."""
    rings = [shapes.open_ring(r) for r in outline.rings]
    groups = shapes.nest(rings)
    polygons = []
    for group in groups:
        kept = []
        for k, i in enumerate(group):
            ring = rings[i]
            if simplify_m:
                ring = ring[lines.simplify_ring(ring, simplify_m)]
            if len(ring) < 3:
                if k == 0:  # the outer ring is gone: so is the polygon
                    break
                continue
            kept.append(_positions(ring, outer=k == 0))
        if kept:
            polygons.append(kept)
    if not polygons:
        biggest = max(groups, key=lambda g: abs(shapes.planar_signed_area(rings[g[0]])))
        polygons = [[_positions(rings[biggest[0]], outer=True)]]
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def entity_feature(entity, simplify_m=None):
    """A GeoJSON Feature dict of a search Entity: its outline (outline_geometry; search with
    geometry=True to have one), else its point; id is the place's id, bbox [west, south, east,
    north], properties its name, kind, tier, codes and context (city, region, country)."""
    place = entity.place
    if entity.outline is not None:
        geometry = outline_geometry(entity.outline, simplify_m)
    else:
        geometry = {"type": "Point", "coordinates": _lon_lat(entity.point.lon, entity.point.lat)}
    properties = {"name": place.name, "kind": place.kind.value}
    if place.tier is not None:
        properties["tier"] = place.tier
    properties.update(place.codes)
    for name in ("city", "region", "country"):
        if getattr(entity, name) is not None:
            properties[name] = getattr(entity, name)
    box = entity.bbox
    return {
        "type": "Feature",
        "id": place.id,
        "bbox": [_round(box.west), _round(box.south), _round(box.east), _round(box.north)],
        "geometry": geometry,
        "properties": properties,
    }


def to_geojson(items, simplify_m=None):
    """A FeatureCollection dict of Entities (entity_feature), Outlines (no properties) and
    Features (their properties and id; each outline its own polygon)."""
    features = []
    for item in items:
        if isinstance(item, Entity):
            features.append(entity_feature(item, simplify_m))
        elif isinstance(item, Outline):
            geometry = outline_geometry(item, simplify_m)
            features.append({"type": "Feature", "geometry": geometry, "properties": {}})
        elif isinstance(item, Feature):
            joined = Outline(tuple(ring for o in item.outlines for ring in o.rings))
            found = {"type": "Feature", "geometry": outline_geometry(joined, simplify_m)}
            if item.id is not None:
                found["id"] = item.id
            found["properties"] = dict(item.properties)
            features.append(found)
        else:
            raise TypeError(f"can't write {type(item).__name__} as GeoJSON (Entity, Outline or Feature)")
    return {"type": "FeatureCollection", "features": features}


def write_geojson(items, path, simplify_m=None):
    """Write to_geojson(items, simplify_m) to `path` (UTF-8); returns the path."""
    path = Path(path)
    path.write_text(json.dumps(to_geojson(items, simplify_m), ensure_ascii=False), encoding="utf-8")
    return path


def _positions(ring, outer):
    """A ring's closed GeoJSON position list, counter-clockwise for an outer ring, clockwise for a
    hole (RFC 7946 3.1.6)."""
    if (shapes.planar_signed_area(ring) > 0) != outer:
        ring = ring[::-1]
    out = [_lon_lat(lon, lat) for lat, lon in np.round(ring, COORD_DECIMALS).tolist()]
    out.append(out[0])
    return out


def _lon_lat(lon, lat):
    return [_round(lon), _round(lat)]


def _round(value):
    return round(float(value), COORD_DECIMALS)
