"""Reverse geocoding: the places a person would name for a point.

    from placewise.engine import Geocoder, lookup

    lookup(43.6426, -79.3871).label             # "Toronto, Ontario, Canada"
    geo = Geocoder(packs=[world, us, ca])       # or the store's world and country packs by default
    geo.lookup_many(lats, lons)                 # vectorised, one Result per point

Rules and their constants: placewise.engine.geocoder (the steps), placewise.engine.naming (the
country packs' names, docs/naming.md), placewise.constants.lookup and placewise.constants.naming.
"""

import threading

from .geocoder import Geocoder

__all__ = ["Geocoder", "lookup"]

_default = None
_lock = threading.Lock()


def _make_default():
    """The user's configuration (placewise.toml, environment) and override files apply."""
    from placewise.config import load_settings
    from placewise.overrides import load_overrides

    settings = load_settings()
    return Geocoder(settings=settings, overrides=load_overrides(settings=settings))


def lookup(lat, lon, *, worldview=None, near=True):
    """Geocoder.lookup on a default Geocoder, created on first call from the user's settings and
    overrides (which may download the world pack, unless settings say offline)."""
    global _default
    if _default is None:
        with _lock:
            if _default is None:
                _default = _make_default()
    return _default.lookup(lat, lon, worldview=worldview, near=near)
