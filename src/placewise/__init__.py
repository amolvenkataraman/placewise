"""Offline, two-way geocoding and geo toolkit.

    import placewise
    placewise.lookup(43.6426, -79.3871).label     # "Toronto, Ontario, Canada"

The headline names load on first use, so `import placewise` stays cheap for toolkit-only users.
"""

__version__ = "0.0.1"

# name -> (module, attribute)
_LAZY = {
    "lookup": ("placewise.engine", "lookup"),
    "Geocoder": ("placewise.engine", "Geocoder"),
    "Client": ("placewise.client", "Client"),
    "load_settings": ("placewise.config", "load_settings"),
    "load_overrides": ("placewise.overrides", "load_overrides"),
}

__all__ = ["__version__", *_LAZY]


def __getattr__(name):
    if name not in _LAZY:
        raise AttributeError(f"module 'placewise' has no attribute {name!r}")
    import importlib

    module, attr = _LAZY[name]
    value = getattr(importlib.import_module(module), attr)
    globals()[name] = value  # later lookups skip this function
    return value
