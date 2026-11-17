"""Synthetic tracks for the privacy tests. Everything sits in the open Atlantic near 0°N 20°W:
no one lives there, so no test encodes a real person's places."""

import numpy as np

from placewise.geo import destination, haversine
from placewise.tracks import Track, TrackMeta

HOME = (0.0, -20.0)
WORK = (0.03, -20.05)  # ~6 km from HOME
T0 = 1_767_571_200.0  # 2026-01-05 00:00 UTC, a Monday
KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))


def walk(start, headings_deg, step_m=5.0, t0=T0, dt=2.0, meta=None):
    """A Track stepping step_m metres per point along the given headings."""
    lats, lons = [start[0]], [start[1]]
    for heading in headings_deg:
        lat, lon = destination(lats[-1], lons[-1], heading, step_m / 1000)
        lats.append(lat)
        lons.append(lon)
    n = len(lats)
    return Track(time=t0 + np.arange(n) * dt, lat=lats, lon=lons, meta=meta)


def street_route(bearing, rng, length_m=1500.0, step_m=5.0, **kwargs):
    """Leaves `start` (HOME by default) roughly towards `bearing` along straight legs of 40-160 m
    that each turn up to 80° off it, like a route through streets: always making progress outward,
    but not radially."""
    start = kwargs.pop("start", HOME)
    headings = []
    while len(headings) * step_m < length_m:
        leg = int(rng.uniform(40, 160) / step_m)
        headings += [bearing + rng.uniform(-80, 80)] * leg
    return walk(start, headings, step_m, **kwargs)


def straight(start, end, n, t0=T0, dt=2.0, meta=None):
    lat = np.linspace(start[0], end[0], n)
    lon = np.linspace(start[1], end[1], n)
    return Track(time=t0 + np.arange(n) * dt, lat=lat, lon=lon, meta=meta)


def distance_m(lat, lon, point):
    return np.asarray(haversine(lat, lon, point[0], point[1])) * 1000


def along_path_m(track):
    """Cumulative distance from each segment's start."""
    out = np.zeros(len(track))
    for start, end in zip(track.segments, (*track.segments[1:], len(track)), strict=True):
        steps = (
            np.asarray(
                haversine(
                    track.lat[start : end - 1],
                    track.lon[start : end - 1],
                    track.lat[start + 1 : end],
                    track.lon[start + 1 : end],
                )
            )
            * 1000
        )
        out[start:end] = np.r_[0.0, np.cumsum(steps)]
    return out


def same_track(a, b):
    return (
        a.columns == b.columns
        and a.segments == b.segments
        and a.meta == b.meta
        and all(np.array_equal(getattr(a, c), getattr(b, c)) for c in a.columns)
    )


RIDE_META = TrackMeta(name="Morning ride", activity="cycling", device="Some GPS", source="ride.fit")
