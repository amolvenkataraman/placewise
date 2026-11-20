"""Places and answers: what `lookup` returns for a point and `find` returns for a name."""

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from placewise.geo.distances import haversine

from ._base import Model, set_field
from .geometry import BBox, Outline, Point


class _Named:
    """repr as Python reads it back (`PlaceKind.PARK`), so a Result's repr round-trips through eval."""

    __slots__ = ()

    def __repr__(self):
        return f"{type(self).__name__}.{self.name}"


class _Card:
    """`str()` is the readable card, always plain text (placewise.model.display); `card()` colours
    it on a terminal; `repr` stays the dataclass's."""

    __slots__ = ()

    def __str__(self):
        return self.card(color=False)

    def card(self, color=None, width=None):
        """The text card. color: True, False, or None for colour only when stdout is a terminal
        (NO_COLOR unset); width: at most this many columns (default 100)."""
        from .display import text

        return text.card(self, color, width or text.const.WIDTH)

    def _repr_html_(self):
        from .display import html

        return html.card(self)


class PlaceKind(_Named, str, Enum):
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


class Relation(_Named, str, Enum):
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
    tier: int | None = None  # parks: 1 national, 2 state / provincial, 3 regional, 4 local
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
class Match(Model):
    """How a Result field's place was found for the point: `within` it (its outline holds the
    point; distance 0), or `near` it, a fallback chosen by distance or score (the nearest town,
    a metro's principal city, a postal city, the polygon beside a shore), with the great-circle km
    to the place's point, or to its box where it has no point; `offshore` for a country whose
    territorial sea holds the point. distance_km is None where it can't be known."""

    relation: Relation
    distance_km: float | None = None

    def __post_init__(self):
        set_field(self, "relation", Relation(self.relation))
        if self.distance_km is not None and self.distance_km < 0:
            raise ValueError("distance can't be negative")


@dataclass(frozen=True, slots=True)
class Disputed(Model):
    """A point inside a disputed area: who claims it, who runs it, and which view was applied."""

    name: str
    claimants: tuple[str, ...]
    administered_by: str | None = None
    applied_view: str = "de_facto"
    views: dict[str, str] = field(default_factory=dict)  # view -> country code it assigns the area to
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
class Entity(_Card, Model):
    """What `find` returns: a place with a point guaranteed inside it, its extent and its context.
    `city`, `region` (state, province) and `country` (ISO alpha-2) say where it is, for telling
    places of one name apart; `alternates` are the same place as found in other data (a city's
    metro area of the same name, a park's point record).

    `context_matches` says, for each of city, region and country that is set, how it was found for
    `point`, as Result.matches has it (`within`, `near` a fallback, `offshore`; distance_km).
    `context_certain` is False when the country or region isn't guaranteed: taken from offshore or
    as the nearest polygon rather than one holding the point, or the point is within
    constants.search.CONTEXT_BORDER_KM of another country's or region's coarse outline
    (docs/search.md, "How sure the context is"). True when there is no context to doubt."""

    place: Place
    point: Point
    bbox: BBox
    radius_km: float  # farthest outline vertex from `point`
    outline: Outline | None = None
    city: str | None = None
    region: str | None = None
    country: str | None = None
    score: float | None = None
    alternates: tuple[Place, ...] = ()
    context_matches: dict[str, Match] = field(default_factory=dict)  # city/region/country -> Match
    context_certain: bool = True

    def __post_init__(self):
        if self.radius_km < 0:
            raise ValueError("radius can't be negative")
        set_field(self, "alternates", tuple(self.alternates))

    def geojson(self, simplify_m=None):
        """This entity as a GeoJSON Feature dict, (lon, lat) order: its outline (search with
        geometry=True for one) as a Polygon or MultiPolygon, else its point; id the place's id,
        properties its name, kind, codes and context. simplify_m: the outline within that many
        metres of the original (placewise.io.entity_feature)."""
        from placewise.io.geojson import entity_feature

        return entity_feature(self, simplify_m)

    def contains(self, lat, lon):
        """Which points lie in this entity: inside its outline when it has one, otherwise within
        radius_km of its point (so points still work for things known only as a location)."""
        if self.outline is not None:
            return self.outline.contains(lat, lon)
        inside = np.asarray(haversine(self.point.lat, self.point.lon, lat, lon)) <= self.radius_km
        return bool(inside) if inside.ndim == 0 else inside


@dataclass(frozen=True, slots=True)
class Result(_Card, Model):
    """What `lookup` returns for a point. `sources` maps each field to the layer or rule that set it;
    `matches` says for each place field whether the point is inside that place or it was the
    nearest fallback, and how far (Match).

    Three names per point (docs/naming.md): `sublocality` (what a local adds: Mission District),
    `locality` (the municipality, corrected for how people talk) and `city` (what you'd tell someone
    far away). The worldview applied shows in `disputed` where it matters, not on every answer."""

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
    postal: Place | None = None  # ZIP Code area (ZCTA), forward sortation area, PIN code area
    tz: str | None = None
    regions: tuple[Place, ...] = ()  # smallest first
    within: tuple[Place, ...] = ()  # parks, campuses ... most significant first (docs/parks.md)
    near: tuple[Nearby, ...] = ()
    airport: Nearby | None = None
    water: Nearby | None = None
    disputed: Disputed | None = None
    relative: Relative | None = None
    sources: dict[str, str] = field(default_factory=dict)
    matches: dict[str, Match] = field(default_factory=dict)  # place field -> how it was found
    data_version: str | None = None

    def __post_init__(self):
        Point(self.lat, self.lon)  # validates

    @property
    def city_within(self):
        """Whether the point lies inside the city (not a nearest-town or metro fallback)."""
        return _within(self.matches.get("city"))

    @property
    def locality_within(self):
        return _within(self.matches.get("locality"))

    @property
    def city_km(self):
        """km from the point to the city: 0.0 inside it, None when unknown or no city."""
        m = self.matches.get("city")
        return m.distance_km if m is not None else None

    @property
    def certain(self):
        """Whether the country and admin1 hold the point (not taken from offshore or as the nearest
        polygon). Fields set by an override count as sure. Unlike Entity.context_certain it doesn't
        measure the distance to a border."""
        return all(_within(m) for f in ("country", "admin1") if (m := self.matches.get(f)) is not None)

    @property
    def cc(self):
        """ISO 3166-1 alpha-2 code of the country, if known."""
        return self.country.codes.get("iso2") if self.country else None


def _within(match):
    return match is not None and match.relation == Relation.WITHIN
