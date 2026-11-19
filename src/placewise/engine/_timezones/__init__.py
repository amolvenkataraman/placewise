"""Time zones (docs/timezones.md): from the zones the packs give their admin units (zones.py), and
from the `timezones` layers of packs built before the zones moved onto those units (legacy.py)."""

from .zones import Timezones

__all__ = ["Timezones"]
