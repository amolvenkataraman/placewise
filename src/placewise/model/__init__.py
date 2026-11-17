"""placewise's data model: frozen, typed dataclasses shared by the library, client, server and caches.

Every type round-trips through plain dicts (`to_dict` / `from_dict`), so JSON responses, cached
answers and TOML configuration all map onto the same objects.
"""

from .attribution import PackInfo, Source
from .geometry import BBox, Feature, Outline, Point
from .overrides import (
    Add,
    Alias,
    AreaSelector,
    CityRule,
    Hide,
    Label,
    Layer,
    OverrideSet,
    RegionRule,
    Rename,
    Tune,
)
from .places import AppPlace, Disputed, Entity, Nearby, Place, PlaceKind, Relation, Relative, Result
from .presence import DayPresence, PresenceDays
from .privacy import PrivacyPolicy, PrivacyZone
from .settings import (
    ComplianceSettings,
    DataSettings,
    LabelSettings,
    NameSettings,
    NearSettings,
    ServerSettings,
    Settings,
    WorldviewSettings,
)
from .world import Country, CountryGroup, Currency, Membership, Profile, Statistic, Subregion

__all__ = [
    "Add",
    "Alias",
    "AppPlace",
    "AreaSelector",
    "BBox",
    "CityRule",
    "ComplianceSettings",
    "Country",
    "CountryGroup",
    "Currency",
    "DataSettings",
    "DayPresence",
    "Disputed",
    "Entity",
    "Feature",
    "Hide",
    "Label",
    "LabelSettings",
    "Layer",
    "Membership",
    "NameSettings",
    "NearSettings",
    "Nearby",
    "Outline",
    "OverrideSet",
    "PackInfo",
    "Place",
    "PlaceKind",
    "Point",
    "PresenceDays",
    "PrivacyPolicy",
    "PrivacyZone",
    "Profile",
    "RegionRule",
    "Relation",
    "Relative",
    "Rename",
    "Result",
    "ServerSettings",
    "Settings",
    "Source",
    "Statistic",
    "Subregion",
    "Tune",
    "WorldviewSettings",
]
