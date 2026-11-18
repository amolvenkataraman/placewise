"""Settings: everything a user can set in placewise.toml. Defaults live in placewise.constants.defaults."""

from dataclasses import dataclass, field

from placewise.constants import defaults

from ._base import Model, set_field

_SPECIAL_VIEWS = {"de_facto", "UN", "disputed"}


def _check_choice(name, value, choices):
    if value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(sorted(choices))}, not {value!r}")


def _is_country_code(code):
    """ISO 3166-1 alpha-2 ("IN") or a 3166-2 subdivision ("UA-43")."""
    country, _, sub = code.partition("-")
    return len(country) == 2 and country.isalpha() and country.isupper() and (not sub or sub.isalnum())


@dataclass(frozen=True, slots=True)
class WorldviewSettings(Model):
    order: tuple[str, ...] = defaults.WORLDVIEW  # first party with a view on an area decides
    lock: bool = False  # operator-only: ignore per-call and per-request orders
    conflict: str = "ignore"  # with a lock, what to do with a request asking for another order

    def __post_init__(self):
        set_field(self, "order", tuple(self.order))
        if not self.order:
            raise ValueError("worldview order can't be empty")
        for view in self.order:
            if view not in _SPECIAL_VIEWS and not (len(view) == 2 and _is_country_code(view)):
                raise ValueError(
                    f"worldview entries are ISO country codes or one of {sorted(_SPECIAL_VIEWS)}: {view!r}"
                )
        _check_choice("worldview conflict", self.conflict, {"ignore", "reject"})


@dataclass(frozen=True, slots=True)
class NameSettings(Model):
    prefer: str = defaults.NAMES_PREFER

    def __post_init__(self):
        _check_choice("names.prefer", self.prefer, {"official", "colloquial"})


@dataclass(frozen=True, slots=True)
class LabelSettings(Model):
    style: str = defaults.LABEL_STYLE
    template: str | None = None  # e.g. "{within}, {city}"; overrides style
    parks: bool = defaults.LABEL_PARKS  # in a national or state park: "<locality>, <park>"

    def __post_init__(self):
        _check_choice("label.style", self.style, {"locality", "city"})


@dataclass(frozen=True, slots=True)
class NearSettings(Model):
    """How far counts as "near", km, per layer and tier."""

    park_tier1: float = defaults.NEAR_KM["park_tier1"]
    park_tier2: float = defaults.NEAR_KM["park_tier2"]
    park_tier3: float = defaults.NEAR_KM["park_tier3"]
    lake_large: float = defaults.NEAR_KM["lake_large"]
    lake: float = defaults.NEAR_KM["lake"]
    river: float = defaults.NEAR_KM["river"]
    coast: float = defaults.NEAR_KM["coast"]
    airport: float = defaults.NEAR_KM["airport"]
    notable_urban: float = defaults.NEAR_KM["notable_urban"]
    notable_rural: float = defaults.NEAR_KM["notable_rural"]
    max_near: int = defaults.MAX_NEAR

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            if getattr(self, name) < 0:
                raise ValueError(f"near.{name} can't be negative")


@dataclass(frozen=True, slots=True)
class DataSettings(Model):
    offline: bool = False  # never download; a missing pack is an error that names it
    auto_update: str = defaults.AUTO_UPDATE
    pin: str | None = None  # hold a data version, e.g. "2026.11"
    mirrors: tuple[str, ...] = ()
    data_dir: str | None = None
    index_url: str | None = None  # where index.json lives; None means the published default

    def __post_init__(self):
        _check_choice("data.auto_update", self.auto_update, {"never", "weekly"})
        set_field(self, "mirrors", tuple(self.mirrors))


@dataclass(frozen=True, slots=True)
class ServerSettings(Model):
    host: str = defaults.SERVER_HOST
    port: int = defaults.SERVER_PORT
    require_keys: bool = True  # API keys for anything but localhost
    log_coordinates: bool = False  # coordinates reveal where people live
    max_batch: int = defaults.SERVER_MAX_BATCH
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self):
        if not 1 <= self.port <= 65535:
            raise ValueError("server.port must be 1-65535")
        if self.max_batch < 1:
            raise ValueError("server.max_batch must be at least 1")
        set_field(self, "cors_origins", tuple(self.cors_origins))


@dataclass(frozen=True, slots=True)
class ComplianceSettings(Model):
    answer_countries_block: tuple[str, ...] = ()  # areas this instance won't describe
    clients_block: tuple[str, ...] = ()  # client regions this instance won't serve
    client_country_from: str | None = None  # "header:X-Client-Country" or "ipdb:/path/file.mmdb"

    def __post_init__(self):
        for name in ("answer_countries_block", "clients_block"):
            codes = tuple(getattr(self, name))
            if bad := [c for c in codes if not _is_country_code(c)]:
                raise ValueError(f"compliance.{name}: not ISO 3166 codes: {bad}")
            set_field(self, name, codes)


@dataclass(frozen=True, slots=True)
class Settings(Model):
    worldview: WorldviewSettings = field(default_factory=WorldviewSettings)
    names: NameSettings = field(default_factory=NameSettings)
    label: LabelSettings = field(default_factory=LabelSettings)
    near: NearSettings = field(default_factory=NearSettings)
    data: DataSettings = field(default_factory=DataSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    compliance: ComplianceSettings = field(default_factory=ComplianceSettings)
