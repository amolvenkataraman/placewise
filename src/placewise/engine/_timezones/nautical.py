"""Nautical time zones: the zone of a point at sea beyond every country's territorial sea.

Ships keep "nautical" (zone) time: 15-degree bands of longitude centred on multiples of 15 degrees,
UTC+n east of Greenwich and UTC-n west, with the bands at 172.5 E to 180 and 180 to 172.5 W being
UTC+12 and UTC-12 (the antimeridian splits the 15-degree band there). tzdb names them Etc/GMT-n
for UTC+n (POSIX's inverted sign) and Etc/GMT for UTC. A point on a band's edge goes east.
"""

import numpy as np

_BAND_DEG = 15.0


def offsets(lon):
    """The nautical zone's offset from UTC, whole hours (-12 .. 12), per longitude."""
    return np.clip(np.floor((np.asarray(lon, dtype=np.float64) + _BAND_DEG / 2) / _BAND_DEG), -12, 12).astype(
        np.int64
    )


def zone_names(lon):
    """The tzdb zone name of each longitude's nautical zone: "Etc/GMT+10" at 150 W, "Etc/GMT" at 0."""
    return [name(h) for h in np.atleast_1d(offsets(lon)).tolist()]


def name(hours):
    """tzdb's name for the fixed zone UTC+hours (Etc/ signs are inverted)."""
    return "Etc/GMT" if hours == 0 else f"Etc/GMT{-hours:+d}"
