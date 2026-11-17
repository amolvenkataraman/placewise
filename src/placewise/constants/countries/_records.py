"""The record types the country reference data is written in."""

import functools
from dataclasses import dataclass, field

from .._keys import city_key


@dataclass(frozen=True, eq=False)
class Metro:
    """A metro area: its short name ("GTA"), name, country, every admin1 it reaches into, the names it
    goes by, other names of member cities -> the preferred name, and member cities -> admin1."""

    key: str
    name: str
    country: str  # ISO 3166-1 alpha-2
    admin1: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    city_aliases: dict[str, str] = field(default_factory=dict)
    cities: dict[str, str] = field(default_factory=dict)
    id: str = ""  # stable id: "region:gta"

    @property
    def sole_admin1(self):
        """The admin1, when the metro lies in just one."""
        return self.admin1[0] if len(self.admin1) == 1 else None

    def admin1_of(self, city):
        """The admin1 of a member city, by name, or None."""
        return self._admin1_by_key.get(city_key(city))

    @functools.cached_property
    def _admin1_by_key(self):
        """city key -> admin1 of the first member city with that key."""
        out = {}
        for name, code in self.cities.items():
            out.setdefault(city_key(name), code)
        return out


@dataclass(frozen=True)
class CityAlias:
    """Another name of a city ("YYZ", "Philly") and the name placewise prefers."""

    city: str
    admin1: str | None
    country: str
    metro: Metro | None = None  # the metro listing the city, if any


@dataclass(frozen=True)
class Candidate:
    """One place a shared name can mean, with a rough prior weight for location strings."""

    country: str
    admin1: str | None = None
    admin1_name: str | None = None  # for admin1 codes no subregion table here knows
    weight: float = 1.0


@dataclass(frozen=True)
class NameClash:
    """A name that is both an admin1 of one country and a country itself ("Georgia")."""

    admin1: str
    admin1_country: str
    country: str
    country_cities: tuple[str, ...] = ()  # cities that settle it for the country
