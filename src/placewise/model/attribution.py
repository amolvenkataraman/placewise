"""Data sources and packs. Constructing a Source is the licence gate: denied or unusable sources fail here."""

from dataclasses import dataclass, field

from placewise.constants import licences

from ._base import Model, set_field


@dataclass(frozen=True, slots=True)
class Source(Model):
    id: str
    name: str
    url: str
    licence: str  # SPDX identifier, or LicenseRef- for ones SPDX lacks
    credit: str  # the exact attribution line apps show
    retrieved: str | None = None
    changes: str | None = None  # what the build did to it
    used_in: tuple[str, ...] = ()  # pack files containing it
    derived_database: str | None = None  # ODbL: where the derived data and recipe are offered
    downloads: dict[str, str] = field(default_factory=dict)  # name -> URL the build fetches
    notes: str | None = None  # terms worth knowing, quirks, why it was chosen

    def __post_init__(self):
        if not all((self.id, self.name, self.url, self.credit)):
            raise ValueError("a source needs an id, name, url and credit line")
        if self.id in licences.DENIED_SOURCES:
            raise ValueError(f"{self.id!r} is on the deny list: its terms forbid redistribution")
        if self.licence not in licences.KNOWN:
            raise ValueError(f"unknown or unusable licence {self.licence!r} for {self.id!r}")
        if self.licence in licences.NEEDS_DERIVED_DATABASE and not self.derived_database:
            raise ValueError(f"{self.licence} source {self.id!r} needs a derived_database offer URL")
        set_field(self, "used_in", tuple(self.used_in))

    @property
    def share_alike(self):
        """Share-alike sources may only feed the separate share-alike pack."""
        return self.licence in licences.SHARE_ALIKE


@dataclass(frozen=True, slots=True)
class PackInfo(Model):
    name: str  # "world", "can", "usa-nature" ... (countries by lower-case ISO alpha-3)
    version: str  # CalVer data version, e.g. "2026.11"
    schema: int  # pack format version; code refuses schemas it can't read
    sha256: str
    size_bytes: int
    sources: tuple[str, ...] = ()

    def __post_init__(self):
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        if self.schema < 1 or self.size_bytes < 0:
            raise ValueError("schema must be >= 1 and size can't be negative")
        set_field(self, "sources", tuple(self.sources))
