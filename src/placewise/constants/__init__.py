"""Every constant placewise uses, one module per subject, so each value has exactly one home.

The modules load on first use (`placewise.constants.wgs84`, `from placewise.constants import
fit`), so importing one subject never pays for the others, the country tables above all."""

import importlib

__all__ = [
    "codab",
    "config",
    "countries",
    "crs",
    "defaults",
    "distance",
    "earth",
    "fit",
    "geohash",
    "gpx",
    "kml",
    "licences",
    "location_filter",
    "location_text",
    "lookup",
    "naming",
    "nmea",
    "overrides",
    "packs",
    "plus_codes",
    "polylines",
    "privacy",
    "server",
    "speed",
    "store",
    "sun",
    "tcx",
    "track_files",
    "tracks",
    "utm",
    "water",
    "web_mercator",
    "wgs84",
    "work_modes",
    "world",
    "worldviews",
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module 'placewise.constants' has no attribute {name!r}")
    return importlib.import_module(f".{name}", __name__)  # the import binds it here too


def __dir__():
    return sorted({*globals(), *__all__})
