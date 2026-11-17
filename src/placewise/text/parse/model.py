"""The parsed-location types: LocationPart, ParsedLocation, and the Gazetteer protocol."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from placewise.constants import countries
from placewise.constants.work_modes import MODES as WORK_MODES
from placewise.constants.work_modes import REMOTE
from placewise.model._base import Model, set_field
from placewise.model.places import Place


@runtime_checkable
class Gazetteer(Protocol):
    """What `parse_location` needs from the lookup layer to confirm a city."""

    def match(self, city: str, country_iso2: str | None, admin1_code: str | None) -> Place | None: ...


@dataclass(frozen=True, slots=True)
class LocationPart(Model):
    """One place named in a location string. `admin1_code` is the subdivision code without its
    country ("ON", "CA", "KA"); `region` is the metro id when one is named or the city is listed in
    one ("GTA", "Bay Area"). `span` is (start, end) into the raw string. `remote` marks a place a
    remote listing is limited to. `alternatives` are the other readings, less likely, same span."""

    city: str | None = None
    admin1_code: str | None = None
    admin1_name: str | None = None
    country_iso2: str | None = None
    region: str | None = None
    confidence: float = 1.0
    span: tuple[int, int] = (0, 0)
    city_verified: bool = False
    remote: bool = False
    place: Place | None = None
    alternatives: tuple["LocationPart", ...] = ()

    def __post_init__(self):
        set_field(self, "span", tuple(self.span))
        set_field(self, "alternatives", tuple(self.alternatives))
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def iso_3166_2(self):
        """ "CA-ON", when both the country and the admin1 are known."""
        if self.country_iso2 and self.admin1_code:
            return f"{self.country_iso2}-{self.admin1_code}"
        return None

    @property
    def label(self):
        """Short text for logs: "Toronto, ON", "GTA", "Ontario", "Canada"."""
        if self.city:
            return f"{self.city}, {self.admin1_code}" if self.admin1_code else self.city
        if self.region:
            return self.region
        if self.admin1_name or self.admin1_code:
            return self.admin1_name or self.admin1_code
        if self.country_iso2:
            country = countries.BY_ALPHA2.get(self.country_iso2)
            return country.name if country else self.country_iso2
        return "?"

    def candidates(self):
        """This reading, then its alternatives."""
        return (self, *self.alternatives)


@dataclass(frozen=True, slots=True)
class ParsedLocation(Model):
    """A location string read into places. `work_mode` is the most permissive mode named (remote,
    then hybrid, then onsite) and `work_modes` every one; `remote_scope` lists what a remote listing is
    limited to: alpha-2 codes, "CC-XX" subdivisions or macro regions ("EMEA"); empty means no
    limit was stated. `unparsed` holds text that named no place."""

    raw: str = ""
    parts: tuple[LocationPart, ...] = ()
    work_mode: str | None = None
    work_modes: tuple[str, ...] = ()
    remote_scope: tuple[str, ...] = ()
    multiple: bool = False
    unparsed: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("parts", "work_modes", "remote_scope", "unparsed"):
            set_field(self, name, tuple(getattr(self, name)))
        if self.work_mode is not None and self.work_mode not in WORK_MODES:
            raise ValueError(f"unknown work mode {self.work_mode!r}")

    @property
    def countries(self):
        """Alpha-2 codes of the parts' likeliest readings, in order, each once."""
        return tuple(dict.fromkeys(p.country_iso2 for p in self.parts if p.country_iso2))

    @property
    def is_remote(self):
        return self.work_mode == REMOTE

    @property
    def ambiguous(self):
        return any(p.alternatives for p in self.parts)
