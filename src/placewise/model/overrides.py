"""Manual overrides: rules that beat the data. Layers stack data < repo < app < local."""

import functools
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo.distances import haversine

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
    """Exactly one of: point + km radius, a bbox, a GeoJSON file path, a place id (the answer
    mentions that place: its admin chain, regions or within) or an ISO 3166-1 alpha-2 country."""

    point: Point | None = None
    km: float | None = None
    bbox: BBox | None = None
    geojson: str | None = None  # relative paths resolve against the overrides file's directory
    place: str | None = None
    country: str | None = None

    def __post_init__(self):
        shapes = (self.point, self.bbox, self.geojson, self.place, self.country)
        if sum(x is not None for x in shapes) != 1:
            raise ValueError("an area is exactly one of: point + km, bbox, geojson, place, country")
        if (self.point is None) != (self.km is None) or (self.km is not None and self.km <= 0):
            raise ValueError("a point area needs a positive km radius (and km needs a point)")
        if self.country is not None:
            code = str(self.country).upper()
            if len(code) != 2 or not code.isalpha():
                raise ValueError(f"area country must be an ISO 3166-1 alpha-2 code, not {self.country!r}")
            set_field(self, "country", code)

    def matches(self, lat, lon, *, cc=None, place_ids=None, base_dir=None):
        """Which points lie in the area. Scalars give a bool; arrays give a bool array.

        Point, bbox and GeoJSON areas need only coordinates. A country area compares `cc` (a code,
        or an array of codes, one per point); a place area looks its id up in `place_ids` (a set
        of ids for one point, or a sequence of sets, one per point)."""
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            found = self._matches_point(float(lat), float(lon), cc, place_ids, base_dir)
            if found is not None:
                return found
        lat, lon = np.broadcast_arrays(np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64))
        if self.point is not None:
            inside = np.asarray(haversine(self.point.lat, self.point.lon, lat, lon)) <= self.km
        elif self.bbox is not None:
            inside = np.asarray(self.bbox.contains(lat, lon))
        elif self.geojson is not None:
            features = _geojson_features(_resolve(self.geojson, base_dir))
            inside = np.zeros(lat.shape, dtype=bool)
            for feature in features:
                inside |= np.asarray(feature.contains(lat, lon))
        elif self.country is not None:
            codes = np.asarray(cc if cc is not None else "", dtype=object)
            inside = np.broadcast_to(
                np.vectorize(_same_country, otypes=[bool])(codes, self.country), lat.shape
            )
        else:
            inside = np.broadcast_to(_has_place(place_ids, self.place, lat.ndim), lat.shape)
        return bool(inside) if inside.ndim == 0 else np.array(inside, dtype=bool)

    def _matches_point(self, lat, lon, cc, place_ids, base_dir):
        """`matches` for one point without numpy, or None where only the array path can tell."""
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return None
        if self.bbox is not None:
            south, west, north, east = self.bbox.as_tuple()
            in_lon = (west <= lon <= east) if west <= east else (lon >= west or lon <= east)
            return south <= lat <= north and in_lon
        if self.country is not None:
            return _same_country(cc, self.country) if cc is None or isinstance(cc, str) else None
        if self.place is not None:
            return place_ids is not None and self.place in place_ids
        if self.point is not None:  # settle the clear cases; the edge is left to numpy's haversine
            d = _haversine_km(self.point.lat, self.point.lon, lat, lon)
            if d > self.km * (1 + _CLEAR) + _CLEAR:
                return False
            if d < self.km * (1 - _CLEAR) - _CLEAR:
                return True
            return None
        boxes = _outline_boxes(_geojson_features(_resolve(self.geojson, base_dir)))
        if not any(s <= lat <= n and w <= lon <= e for s, w, n, e in boxes):
            return False  # each outline tests its box before the polygon
        return None


_BOXES = {}  # id(features) -> (features, their outlines' boxes)


def _outline_boxes(features):
    hit = _BOXES.get(id(features))
    if hit is None or hit[0] is not features:
        if len(_BOXES) >= 256:
            _BOXES.clear()
        boxes = tuple(o.bbox.as_tuple() for f in features for o in f.outlines)
        hit = _BOXES[id(features)] = (features, boxes)
    return hit[1]


_CLEAR = 1e-9  # relative (and km) margin between math's and numpy's haversine, far above rounding


def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * MEAN_RADIUS_KM * math.asin(math.sqrt(min(max(a, 0.0), 1.0)))


def _same_country(code, wanted):
    return isinstance(code, str) and code.upper() == wanted


def _has_place(place_ids, wanted, ndim):
    if place_ids is None:
        return np.asarray(False)
    if ndim == 0:
        return np.asarray(wanted in place_ids)
    return np.array([wanted in (ids or ()) for ids in place_ids], dtype=bool)


def _resolve(path, base_dir):
    path = Path(path).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = Path(base_dir) / path
    return str(path.resolve())


@functools.lru_cache(maxsize=64)
def _geojson_features(path):
    from placewise.io.geojson import read_geojson  # io builds on the model, so import late

    features = read_geojson(path)
    if not features:
        raise ValueError(f"{path}: no polygons in this GeoJSON")
    return tuple(features)


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
    """Show `city` as the display city for one locality id, or for every point in an area."""

    locality: str | None = None  # locality id
    city: str = ""
    origin: str | None = None
    within: AreaSelector | None = None

    def __post_init__(self):
        if not self.city:
            raise ValueError("a city rule needs a city")
        if (self.locality is None) == (self.within is None):
            raise ValueError("a city rule targets exactly one of: locality, within")


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
    within: AreaSelector | None = None  # match this area instead of point + radius_m

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
        """Rules from a parsed overrides file; each rule remembers "file#n" so answers can cite it.
        Errors name the file and the rule number, counted through the file across all tables."""
        where = f"{origin}: " if origin else ""
        if not isinstance(document, dict):
            raise ValueError(f"{where}an overrides document is a mapping of [[type]] tables")
        rules = []
        for table, entries in document.items():
            n = len(rules) + 1
            rule_type = RULE_TYPES.get(table)
            if rule_type is None:
                raise ValueError(
                    f"{where}rule #{n}: unknown override type [[{table}]]; known: {', '.join(RULE_TYPES)}"
                )
            if not isinstance(entries, list | tuple):
                raise ValueError(f"{where}rule #{n}: write [[{table}]] (an array of tables), not [{table}]")
            for entry in entries:
                n = len(rules) + 1
                tag = f"{origin}#{n}" if origin else None
                try:
                    if not isinstance(entry, dict):
                        raise ValueError(f"expected a table, got {type(entry).__name__}")
                    if "origin" in entry:
                        raise ValueError("'origin' is set by the loader, not in the file")
                    rules.append(rule_type.from_dict({**entry, "origin": tag}))
                except (TypeError, ValueError) as e:
                    raise ValueError(f"{where}rule #{n} [[{table}]]: {e}") from e
        return cls(Layer(layer), tuple(rules))
