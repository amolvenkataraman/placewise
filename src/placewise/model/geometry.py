"""Points, bounding boxes and outlines: validated WGS84 geometry in (lat, lon) order."""

from dataclasses import dataclass, field

import numpy as np

from placewise.geo import coords, shapes

from ._base import Model, set_field


@dataclass(frozen=True, slots=True)
class Point(Model):
    lat: float
    lon: float

    def __post_init__(self):
        coords.validate(self.lat, self.lon)
        set_field(self, "lat", float(self.lat))
        set_field(self, "lon", float(self.lon))


@dataclass(frozen=True, slots=True)
class BBox(Model):
    """(south, west, north, east); west > east means the box crosses the antimeridian."""

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self):
        coords.validate((self.south, self.north), (self.west, self.east))
        if self.south > self.north:
            raise ValueError(f"bbox south ({self.south}) is north of its north ({self.north})")
        for name in ("south", "west", "north", "east"):
            set_field(self, name, float(getattr(self, name)))

    @property
    def crosses_antimeridian(self):
        return self.west > self.east

    def as_tuple(self):
        return (self.south, self.west, self.north, self.east)

    def contains(self, lat, lon):
        return shapes.bbox_contains(self.as_tuple(), lat, lon)

    def split(self):
        """One or two boxes that don't cross the antimeridian."""
        return [BBox(*box) for box in shapes.bbox_split(self.as_tuple())]


@dataclass(frozen=True, slots=True)
class Outline(Model):
    """A polygon: outer ring first, then holes; each ring a tuple of (lat, lon) pairs. Containment is
    even-odd over all rings, so the rings of several polygons together (an island state, a park in
    parts) make one outline too."""

    rings: tuple[tuple[tuple[float, float], ...], ...]

    def __post_init__(self):
        rings = tuple(tuple((float(lat), float(lon)) for lat, lon in ring) for ring in self.rings)
        if not rings:
            raise ValueError("an outline needs at least one ring")
        for ring in rings:
            corners = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
            if len(set(corners)) < 3:
                raise ValueError("each ring needs at least three distinct corners")
            lats, lons = zip(*ring, strict=True)
            coords.validate(lats, lons)
        set_field(self, "rings", rings)

    @property
    def bbox(self):
        lats = [lat for ring in self.rings for lat, _ in ring]
        lons = [lon for ring in self.rings for _, lon in ring]
        return BBox(min(lats), min(lons), max(lats), max(lons))

    def contains(self, lat, lon):
        """Which points lie inside (holes excluded). Points outside the bounding box are rejected
        before the exact test, so large point sets cost little more than the points near the shape."""
        lat, lon = np.broadcast_arrays(np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64))
        candidates = np.asarray(self.bbox.contains(lat, lon))
        inside = np.zeros(lat.shape, dtype=bool)
        if candidates.any():
            inside[candidates] = shapes.contains(self.rings, lat[candidates], lon[candidates])
        return bool(inside) if inside.ndim == 0 else inside

    @property
    def area_km2(self):
        return shapes.area(self.rings)

    def to_geojson(self, simplify_m=None):
        """This outline as a GeoJSON geometry dict, (lon, lat) order: a Polygon, or a MultiPolygon
        when its rings make several, each hole under the ring that holds it; simplify_m: within
        that many metres of the original (placewise.io.outline_geometry)."""
        from placewise.io.geojson import outline_geometry

        return outline_geometry(self, simplify_m)


@dataclass(frozen=True, slots=True)
class Feature(Model):
    """A shape with its attributes, as read from GeoJSON or a shapefile: one or more polygons
    (a MultiPolygon is several outlines) plus free-form properties."""

    outlines: tuple[Outline, ...]
    properties: dict[str, object] = field(default_factory=dict)
    id: str | None = None

    def __post_init__(self):
        set_field(self, "outlines", tuple(self.outlines))
        if not self.outlines:
            raise ValueError("a feature needs at least one outline")

    @property
    def bbox(self):
        boxes = [o.bbox for o in self.outlines]
        return BBox(
            min(b.south for b in boxes),
            min(b.west for b in boxes),
            max(b.north for b in boxes),
            max(b.east for b in boxes),
        )

    def contains(self, lat, lon):
        inside = np.logical_or.reduce([np.asarray(o.contains(lat, lon)) for o in self.outlines])
        return bool(inside) if inside.ndim == 0 else inside
