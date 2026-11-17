"""Manual overrides: rules that beat the data. Layers stack data < repo < app < local."""

from dataclasses import dataclass, field
from enum import Enum

from ._base import Model, set_field
from .geometry import BBox, Point
from .places import PlaceKind


class Layer(Enum):
    DATA = "data"  # the packs themselves
    REPO = "repo"  # overrides/ in the repository, inherited by every install
    APP = "app"  # places the calling app passes per call
    LOCAL = "local"  # the user's own files; win over everything

    @property
    def precedence(self):
        return list(Layer).index(self)


@dataclass(frozen=True, slots=True)
class AreaSelector(Model):
    """Exactly one of: point + km radius, a bbox, or a GeoJSON file path."""

    point: Point | None = None
    km: float | None = None
    bbox: BBox | None = None
    geojson: str | None = None

    def __post_init__(self):
        if sum(x is not None for x in (self.point, self.bbox, self.geojson)) != 1:
            raise ValueError("an area is exactly one of: point + km, bbox, geojson")
        if (self.point is None) != (self.km is None) or (self.km is not None and self.km <= 0):
            raise ValueError("a point area needs a positive km radius (and km needs a point)")


# answer fields a `label` rule may set
LABEL_FIELDS = frozenset(
    {"label", "city", "locality", "sublocality", "borough", "region", "admin1", "admin2"}
)


@dataclass(frozen=True, slots=True)
class Rename(Model):
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class Label(Model):
    within: AreaSelector
    fields: dict[str, str]
    origin: str | None = None

    def __post_init__(self):
        if not self.fields:
            raise ValueError("a label rule must set at least one field")
        if bad := sorted(set(self.fields) - LABEL_FIELDS):
            raise ValueError(f"label rules can set {sorted(LABEL_FIELDS)}, not {bad}")


@dataclass(frozen=True, slots=True)
class CityRule(Model):
    locality: str  # locality id
    city: str
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class RegionRule(Model):
    id: str
    label: str | None = None
    aliases: tuple[str, ...] = ()
    kind: str = "vernacular"
    members: dict[str, tuple[str, ...]] = field(default_factory=dict)  # {"ca_cd": ("3518", ...)}
    polygon: str | None = None
    remove: bool = False
    origin: str | None = None

    def __post_init__(self):
        if not self.remove and not (self.members or self.polygon):
            raise ValueError(f"region {self.id!r} needs members or a polygon (or remove = true)")


@dataclass(frozen=True, slots=True)
class Alias(Model):
    text: str
    means: str  # entity id
    country: str | None = None  # only within this country
    near: Point | None = None  # only near this point
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class Hide(Model):
    id: str
    origin: str | None = None


@dataclass(frozen=True, slots=True)
class Add(Model):
    kind: PlaceKind
    name: str
    point: Point
    radius_m: float = 100.0
    id: str | None = None
    origin: str | None = None

    def __post_init__(self):
        set_field(self, "kind", PlaceKind(self.kind))
        if self.radius_m <= 0:
            raise ValueError("radius must be positive")


@dataclass(frozen=True, slots=True)
class Tune(Model):
    id: str | None = None
    kind: PlaceKind | None = None
    tier: int | None = None
    near_km: float | None = None
    fame: float | None = None
    boost: float | None = None
    origin: str | None = None

    def __post_init__(self):
        if (self.id is None) == (self.kind is None):
            raise ValueError("a tune rule targets exactly one of: id, kind")
        if all(v is None for v in (self.tier, self.near_km, self.fame, self.boost)):
            raise ValueError("a tune rule must change something")


# TOML table name -> rule type ([[rename]], [[label]], ...)
RULE_TYPES = {
    "rename": Rename,
    "label": Label,
    "city": CityRule,
    "region": RegionRule,
    "alias": Alias,
    "hide": Hide,
    "add": Add,
    "tune": Tune,
}


@dataclass(frozen=True, slots=True)
class OverrideSet:
    layer: Layer
    rules: tuple

    @classmethod
    def from_dict(cls, layer, document, origin=None):
        """Rules from a parsed overrides file; each rule remembers "file#n" so answers can cite it."""
        rules = []
        for table, entries in document.items():
            rule_type = RULE_TYPES.get(table)
            if rule_type is None:
                raise ValueError(f"unknown override type [[{table}]]; known: {', '.join(RULE_TYPES)}")
            for entry in entries:
                tag = f"{origin}#{len(rules) + 1}" if origin else None
                rules.append(rule_type.from_dict({**entry, "origin": tag}))
        return cls(Layer(layer), tuple(rules))
