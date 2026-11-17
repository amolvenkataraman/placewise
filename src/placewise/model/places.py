"""Places and answers: what `lookup` returns for a point and `find` returns for a name."""

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from placewise.geo.distances import haversine

from ._base import Model, set_field
from .geometry import BBox, Outline, Point


class PlaceKind(str, Enum):
    COUNTRY = "country"
    ADMIN1 = "admin1"  # state, province, region
    ADMIN2 = "admin2"  # county, district
    LOCALITY = "locality"  # the municipality
    SUBLOCALITY = "sublocality"  # neighbourhood, former town
    BOROUGH = "borough"
    REGION = "region"  # vernacular or metro: Bay Area, GTHA
    POSTAL_CODE = "postal_code"
    PARK = "park"  # protected areas of every tier
    WATER = "water"
    AIRPORT = "airport"
    UNIVERSITY = "university"
    BUILDING = "building"
    STATION = "station"
    PEAK = "peak"
    ISLAND = "island"
    BEACH = "beach"
    TRAIL = "trail"
    HIGHWAY = "highway"
    LANDMARK = "landmark"
    SKI_AREA = "ski_area"
    VIEWPOINT = "viewpoint"
    TIMEZONE = "timezone"
    CUSTOM = "custom"  # added by an override or the calling app


class Relation(str, Enum):
    """How a point relates to a place."""

    AT = "at"  # airports, stations, buildings
    WITHIN = "within"  # areas
    NEAR = "near"
    OVER = "over"  # water, in flight
    OFFSHORE = "offshore"
    ON = "on"  # highways, trails


@dataclass(frozen=True, slots=True)
class Place(Model):
    """Anything placewise can name. `id` is stable across data releases ("wikidata:Q180402",
    "geonames:6167865", "census:0646870"), so apps can group by it and keep user renames.
    Holds a dict (codes), so it isn't hashable."""

    id: str
    name: str
    kind: PlaceKind
    point: Point | None = None
    bbox: BBox | None = None
    tier: int | None = None  # parks: 1 national ... 3 local
    codes: dict[str, str] = field(default_factory=dict)  # iata, icao, iso2, postal ...
    aliases: tuple[str, ...] = ()
    source: str | None = None  # attribution source id

    def __post_init__(self):
        if not self.id or not self.name:
            raise ValueError("a place needs an id and a name")
        set_field(self, "kind", PlaceKind(self.kind))
        set_field(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True, slots=True)
class Nearby(Model):
    place: Place
    relation: Relation
    distance_km: float
    bearing_deg: float | None = None  # from the query point to the place
    compass: str | None = None

    def __post_init__(self):
        set_field(self, "relation", Relation(self.relation))
        if self.distance_km < 0:
            raise ValueError("distance can't be negative")


@dataclass(frozen=True, slots=True)
class Disputed(Model):
    """A point inside a disputed area: who claims it, who runs it, and which view was applied."""

    name: str
    claimants: tuple[str, ...]
    administered_by: str | None = None
    applied_view: str = "de_facto"
    views: dict[str, str] = field(default_factory=dict)  # view -> admin1 code it assigns
    locked: bool = False  # the operator locked the worldview; request settings were ignored


@dataclass(frozen=True, slots=True)
class Relative(Model):
    """Where the point is relative to one of the calling app's places ("12 km SW of home")."""

    name: str
    distance_km: float
    bearing_deg: float
    compass: str
    inside: bool


@dataclass(frozen=True, slots=True)
class AppPlace(Model):
    """A place the calling app passes in (home, work); never stored by placewise."""

    name: str
    lat: float
    lon: float
    radius_m: float = 100.0

    def __post_init__(self):
        Point(self.lat, self.lon)  # validates
        if self.radius_m <= 0:
            raise ValueError("radius must be positive")

    @property
    def point(self):
        return Point(self.lat, self.lon)


@dataclass(frozen=True, slots=True)
class Entity(Model):
    """What `find` returns: a place with a point guaranteed inside it, its extent and its context."""

    place: Place
    point: Point
    bbox: BBox
    radius_km: float  # farthest outline vertex from `point`
    outline: Outline | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    score: float | None = None

    def __post_init__(self):
        if self.radius_km < 0:
            raise ValueError("radius can't be negative")

    def contains(self, lat, lon):
        """Which points lie in this entity: inside its outline when it has one, otherwise within
        radius_km of its point (so points still work for things known only as a location)."""
        if self.outline is not None:
            return self.outline.contains(lat, lon)
        inside = np.asarray(haversine(self.point.lat, self.point.lon, lat, lon)) <= self.radius_km
        return bool(inside) if inside.ndim == 0 else inside


@dataclass(frozen=True, slots=True)
class Result(Model):
    """What `lookup` returns for a point. `sources` maps each field to the layer or rule that set it."""

    lat: float
    lon: float
    label: str = ""
    country: Place | None = None
    admin1: Place | None = None
    admin2: Place | None = None
    city: Place | None = None
    locality: Place | None = None
    sublocality: Place | None = None
    borough: Place | None = None
    tz: str | None = None
    regions: tuple[Place, ...] = ()  # smallest first
    within: tuple[Place, ...] = ()  # parks, campuses ... most significant first
    near: tuple[Nearby, ...] = ()
    airport: Nearby | None = None
    water: Nearby | None = None
    disputed: Disputed | None = None
    relative: Relative | None = None
    sources: dict[str, str] = field(default_factory=dict)
    data_version: str | None = None
    worldview: tuple[str, ...] = ()
    worldview_locked: bool = False

    def __post_init__(self):
        Point(self.lat, self.lon)  # validates

    @property
    def cc(self):
        """ISO 3166-1 alpha-2 code of the country, if known."""
        return self.country.codes.get("iso2") if self.country else None
