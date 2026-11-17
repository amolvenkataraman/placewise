"""Trim the ends of each recording, where it starts and stops (often a doorstep).

A fixed trim leaves the cut a known distance from the true start, so the start can be walked back
along the route. The extra per-track jitter, from HMAC(key, track's first timestamp), makes that
distance unknown (within [trim_m, trim_m + jitter_m)) while the same track always trims the same
way, so sharing it twice reveals nothing new.

What it does not hide: the start still lies on the route's continuation within trim_m + jitter_m,
and repeated tracks from one place, each trimmed by a different jitter, bracket it: the trimmed
ends of many tracks fan out around it. Use a privacy zone for places you start from often.
"""

import numpy as np

from ._common import along_path_m, check_key, keyed_uniforms, segment_bounds, select


def trim_jitter_m(track, jitter_m, key):
    """The track's secret extra trim in metres, in [0, jitter_m)."""
    key = check_key(key)
    if jitter_m == 0 or len(track) == 0:
        return 0.0
    return keyed_uniforms(key, "trim-jitter", float(track.time[0]))[0] * jitter_m


def trim_ends(track, trim_m, jitter_m, key):
    """A new Track without the first and last trim_m + jitter metres (along the path) of each
    segment; segments shorter than twice that disappear. One jitter for the whole track."""
    if trim_m < 0 or jitter_m < 0:
        raise ValueError("trim distances can't be negative")
    total = trim_m + trim_jitter_m(track, jitter_m, key)
    if total == 0 or len(track) == 0:
        return track
    s = along_path_m(track)
    keep = np.zeros(len(track), dtype=bool)
    for start, end in segment_bounds(track):
        seg_s = s[start:end]
        keep[start:end] = (seg_s >= total) & (seg_s[-1] - seg_s >= total)
    return select(track, keep)
