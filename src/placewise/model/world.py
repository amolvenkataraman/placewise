"""Countries, their subdivisions, country groups and country profiles (placewise.world returns these)."""

import datetime as dt
import re
from dataclasses import dataclass, field

from placewise.constants.world import DRIVING_SIDES, MEASUREMENT_SYSTEMS, WEEKDAYS

from ._base import Model, set_field

CATEGORIES = ("geographic", "legal")
_ALPHA2 = re.compile(r"[A-Z]{2}")
_ALPHA3 = re.compile(r"[A-Z]{3}")
_NUMERIC = re.compile(r"\d{3}")
_DATE = re.compile(r"\d{4}(-\d{2}-\d{2})?")


def _check(pattern, value, what):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{what} {value!r} is not valid")


def _check_date(value, what):
    """A YYYY or YYYY-MM-DD date, as the group datasets write them; None for unknown."""
    if value is None:
        return
    _check(_DATE, value, what)
    if len(value) == 10:
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{what} {value!r} is no such day") from None


def _one_of(value, allowed, what):
    if value is not None and value not in allowed:
        raise ValueError(f"{what} {value!r} must be one of {', '.join(allowed)}")


@dataclass(frozen=True, slots=True)
class Country(Model):
    """An ISO 3166-1 country or territory. `official_name` only where a source gives one."""

    alpha2: str
    alpha3: str
    numeric: str  # three digits, zero padded
    name: str
    official_name: str | None = None
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        _check(_ALPHA2, self.alpha2, "alpha-2 code")
        _check(_ALPHA3, self.alpha3, "alpha-3 code")
        _check(_NUMERIC, self.numeric, "numeric code")
        if not self.name:
            raise ValueError("a country needs a name")
        set_field(self, "aliases", tuple(self.aliases))


@dataclass(frozen=True, slots=True)
class Subregion(Model):
    """An ISO 3166-2 subdivision: code "CA-ON", short_code "ON", kind "province"; `codes` holds
    other code systems ({"fips": "06"}, {"sgc": "35"})."""

    code: str
    short_code: str
    name: str
    kind: str  # state, province, territory, union territory, district, country ...
    country: str  # ISO 3166-1 alpha-2
    aliases: tuple[str, ...] = ()
    codes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        _check(_ALPHA2, self.country, "country code")
        if self.code != f"{self.country}-{self.short_code}":
            raise ValueError(f"code {self.code!r} must be {self.country}-{self.short_code}")
        if not self.name or not self.kind:
            raise ValueError("a subregion needs a name and a kind")
        set_field(self, "aliases", tuple(self.aliases))
        set_field(self, "codes", dict(self.codes))


@dataclass(frozen=True, slots=True)
class Membership(Model):
    """A country in a group: since its first day and until its last (None: unknown or ongoing;
    a year alone means that year). `suspended_since` when the organisation has suspended it."""

    country: str
    since: str | None = None
    until: str | None = None
    suspended_since: str | None = None

    def __post_init__(self):
        _check(_ALPHA2, self.country, "country code")
        for name in ("since", "until", "suspended_since"):
            _check_date(getattr(self, name), name)
        if self.since and self.until and self.until[:4] < self.since[:4]:
            raise ValueError(f"{self.country}: until {self.until} is before since {self.since}")


@dataclass(frozen=True, slots=True)
class CountryGroup(Model):
    """A group of countries: geographic (continents, UN M49 regions, business regions) or legal
    (unions, treaties, alliances), with every membership it has had. `other_members` are members
    without an ISO code: other groups' ids ("legal:eu") or entity names."""

    id: str
    name: str
    aliases: tuple[str, ...]
    kind: str
    category: str  # "geographic" or "legal"
    members: tuple[Membership, ...]
    source: str  # an https URL, or "convention"
    notes: str | None = None
    other_members: tuple[str, ...] = ()

    def __post_init__(self):
        _one_of(self.category, CATEGORIES, "category")
        set_field(self, "aliases", tuple(self.aliases))
        set_field(self, "members", tuple(self.members))
        set_field(self, "other_members", tuple(self.other_members))


@dataclass(frozen=True, slots=True)
class Currency(Model):
    code: str  # ISO 4217
    name: str | None = None  # English (CLDR)
    symbol: str | None = None  # English (CLDR): "CA$"
    narrow_symbol: str | None = None  # "$"

    def __post_init__(self):
        _check(_ALPHA3, self.code, "currency code")


@dataclass(frozen=True, slots=True)
class Statistic(Model):
    """A figure with where it comes from and the year it describes (None when the source gives none)."""

    value: float
    source: str
    year: int | None = None


@dataclass(frozen=True, slots=True)
class Profile(Model):
    """A country's (or subregion's) facts and conventions; None (or empty) where no source has them."""

    code: str  # alpha-2, or ISO 3166-2 for a subregion
    name: str
    kind: str  # "country", or the subregion's kind
    alpha2: str
    alpha3: str
    capital: str | None = None
    continent: str | None = None
    currency: Currency | None = None
    calling_code: str | None = None  # "+1"
    languages: tuple[str, ...] = ()  # BCP 47, most spoken first
    measurement_system: str | None = None  # metric, US, imperial-mixed
    driving_side: str | None = None  # left, right
    first_day_of_week: str | None = None  # monday ... sunday
    date_format: str | None = None  # CLDR short date pattern: "y-MM-dd"
    locale: str | None = None  # the CLDR locale date_format comes from
    tld: str | None = None
    time_zones: tuple[str, ...] = ()  # IANA
    population: Statistic | None = None
    area_km2: Statistic | None = None
    neighbours: tuple[str, ...] = ()  # alpha-2
    postal_code_format: str | None = None  # GeoNames: "@#@ #@#"
    postal_code_regex: str | None = None

    def __post_init__(self):
        _check(_ALPHA2, self.alpha2, "alpha-2 code")
        _check(_ALPHA3, self.alpha3, "alpha-3 code")
        _one_of(self.measurement_system, MEASUREMENT_SYSTEMS, "measurement_system")
        _one_of(self.driving_side, DRIVING_SIDES, "driving_side")
        _one_of(self.first_day_of_week, WEEKDAYS, "first_day_of_week")
        for name in ("languages", "time_zones", "neighbours"):
            set_field(self, name, tuple(getattr(self, name)))
