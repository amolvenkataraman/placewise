"""Time zones (docs/naming.md, "Time zones"): from the zones the packs give their admin units (zones.py), and
from the `timezones` layers of packs built before the zones moved onto those units (legacy.py);
at sea, beyond every territorial sea, the nautical zone of the longitude (nautical.py)."""

from .zones import Timezones

__all__ = ["Timezones"]
