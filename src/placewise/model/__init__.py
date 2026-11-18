"""placewise's data model: frozen, typed dataclasses shared by the library, client, server and caches.

Every type round-trips through plain dicts (`to_dict` / `from_dict`), so JSON responses, cached
answers and TOML configuration all map onto the same objects.
"""

import importlib

# name -> submodule; imported on first use, so `placewise.model` costs nothing until then
_LAZY = {
    "PackInfo": "attribution",
    "Source": "attribution",
    "BBox": "geometry",
    "Feature": "geometry",
    "Outline": "geometry",
    "Point": "geometry",
    "Add": "overrides",
    "Alias": "overrides",
    "AreaSelector": "overrides",
    "CityRule": "overrides",
    "Hide": "overrides",
    "Label": "overrides",
    "Layer": "overrides",
    "OverrideSet": "overrides",
    "RegionRule": "overrides",
    "Rename": "overrides",
    "Tune": "overrides",
    "AppPlace": "places",
    "Disputed": "places",
    "Entity": "places",
    "Match": "places",
    "Nearby": "places",
    "Place": "places",
    "PlaceKind": "places",
    "Relation": "places",
    "Relative": "places",
    "Result": "places",
    "DayPresence": "presence",
    "PresenceDays": "presence",
    "PrivacyPolicy": "privacy",
    "PrivacyZone": "privacy",
    "ComplianceSettings": "settings",
    "DataSettings": "settings",
    "LabelSettings": "settings",
    "NameSettings": "settings",
    "NearSettings": "settings",
    "ServerSettings": "settings",
    "Settings": "settings",
    "WorldviewSettings": "settings",
    "Country": "world",
    "CountryGroup": "world",
    "Currency": "world",
    "Membership": "world",
    "Profile": "world",
    "Statistic": "world",
    "Subregion": "world",
}

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
    "Match",
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


_SUBMODULES = frozenset(_LAZY.values())


def __getattr__(name):
    if name in _SUBMODULES:  # placewise.model.geometry and the like, as plain attributes
        return importlib.import_module(f".{name}", __name__)
    if name not in _LAZY:
        raise AttributeError(f"module 'placewise.model' has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{_LAZY[name]}", __name__), name)
    globals()[name] = value  # later lookups skip this function
    return value


def __dir__():
    return sorted({*globals(), *__all__})
