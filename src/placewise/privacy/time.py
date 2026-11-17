"""Coarser and shifted timestamps.

Exact times reveal routine (when you leave home, how long you stay) and link a track to other
records of the same moment. Flooring to the minute, hour or day keeps order at the chosen grain;
day floors fall on UTC midnight. Shifting moves a whole track by an offset you choose, hiding the
real date while keeping durations, so it protects only while the offset stays secret, and the
sun, weather or events in a track's surroundings can still date it.
"""

import math

import numpy as np

from placewise.constants.privacy import TIME_RESOLUTION_S

from ._common import replace_columns


def coarsen_times(track, resolution):
    """A new Track with times floored to "minute", "hour" or "day" (UTC)."""
    try:
        step = TIME_RESOLUTION_S[resolution]
    except KeyError:
        raise ValueError(
            f"resolution must be one of {', '.join(TIME_RESOLUTION_S)}; got {resolution!r}"
        ) from None
    return replace_columns(track, time=np.floor(track.time / step) * step)


def shift_times(track, offset_s):
    """A new Track with every time moved by offset_s seconds."""
    if not math.isfinite(offset_s):
        raise ValueError("offset_s must be finite")
    if offset_s == 0:
        return track
    return replace_columns(track, time=track.time + offset_s)
