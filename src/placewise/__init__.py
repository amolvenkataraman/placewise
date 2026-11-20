"""Offline, two-way geocoding and geo toolkit.

    import placewise
    placewise.lookup(43.6426, -79.3871).label     # "Toronto, Ontario, Canada"
    placewise.find("Yosemite")[0].bbox             # name in, place out
    placewise.country("can").name                  # "Canada"  (placewise.world has the rest)

The headline names load on first use, so `import placewise` stays cheap for toolkit-only users.
"""

__version__ = "0.1.0a2"

# name -> (module, attribute)
_LAZY = {
    "lookup": ("placewise.engine", "lookup"),
    "Geocoder": ("placewise.engine", "Geocoder"),
    "find": ("placewise.search", "find"),
    "get": ("placewise.search", "get"),
    "outline": ("placewise.search", "outline"),
    "suggest": ("placewise.search", "suggest"),
    "Client": ("placewise.service", "Client"),
    "load_settings": ("placewise.config", "load_settings"),
    "load_overrides": ("placewise.overrides", "load_overrides"),
    "world": ("placewise.world", None),  # the module itself
    "country": ("placewise.world", "country"),
    "countries": ("placewise.world", "countries"),
    "profile": ("placewise.world", "profile"),
}

__all__ = ["__version__", *_LAZY]


def __getattr__(name):
    if name not in _LAZY:
        raise AttributeError(f"module 'placewise' has no attribute {name!r}")
    import importlib

    module, attr = _LAZY[name]
    imported = importlib.import_module(module)
    value = imported if attr is None else getattr(imported, attr)
    globals()[name] = value  # later lookups skip this function
    return value
