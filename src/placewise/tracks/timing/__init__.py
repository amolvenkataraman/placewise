"""Tracks against time: where the track was at any moment.

- positions: position_at, geotag (photo positions) and resample (regular spacing);
- clock: estimate_clock_offset, a camera clock's offset from the track's time.

Track times must be non-decreasing.
"""

from .clock import ClockOffset, estimate_clock_offset
from .positions import Geotags, geotag, position_at, resample

__all__ = ["ClockOffset", "Geotags", "estimate_clock_offset", "geotag", "position_at", "resample"]
