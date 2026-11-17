"""Privacy zones: remove the parts of a track near sensitive places without pointing at them.

Cutting a track exactly where it crosses a zone's circle leaks the circle: endpoints from a few
tracks leaving home in different directions lie on it, and three points fix its centre. So each
zone gets a secret extra distance, HMAC(key, zone name) scaled into [0, radius), and the track is cut
that much further *along the path* (before entering and after leaving). Paths wind, so the extra
along the path covers a different straight-line distance on every route, and cut points scatter
over an annulus between radius and twice the radius instead of sitting on one circle.

What it does not hide: the hole itself. Given many tracks leaving in all directions, the centre of
the empty region still estimates the zone's centre to within roughly its (radius + extra); the cut
only stops the endpoints from giving it away exactly. Routes that leave in a straight radial line
cover the extra radially, so their cut points do share a circle (of secret radius). Keep zone
names, radii and the key stable: each change draws a new extra, and releases under different
extras can be intersected.
"""

import numpy as np

from placewise.geo import haversine

from .._common import along_path_m, check_key, keyed_uniforms, segment_bounds, select


def zone_extra_m(zone, key):
    """The zone's secret extra cut distance in metres, in [0, zone.radius_m)."""
    return keyed_uniforms(check_key(key), "zone-extra", zone.name)[0] * zone.radius_m


def apply_zones(track, zones, key):
    """A new Track without the points within each zone, nor those within the zone's secret extra
    distance of them along the path. Segments split where points were removed."""
    key = check_key(key)
    zones = tuple(zones)
    if not zones or len(track) == 0:
        return track
    s = along_path_m(track)
    drop = np.zeros(len(track), dtype=bool)
    for zone in zones:
        inside = np.asarray(haversine(track.lat, track.lon, zone.point.lat, zone.point.lon)) * 1000
        inside = inside <= zone.radius_m
        if inside.any():
            drop |= _near_along_path(s, inside, zone_extra_m(zone, key), segment_bounds(track))
    return select(track, ~drop)


def _near_along_path(s, inside, extra, bounds):
    """Points within `extra` metres along their segment's path of any inside point."""
    near = np.zeros(len(s), dtype=bool)
    for start, end in bounds:
        seg_s, seg_in = s[start:end], inside[start:end]
        if not seg_in.any():
            continue
        # s only grows along a segment, so the nearest inside point behind is a running max and
        # the nearest ahead a reversed running min
        behind = np.maximum.accumulate(np.where(seg_in, seg_s, -np.inf))
        ahead = np.minimum.accumulate(np.where(seg_in, seg_s, np.inf)[::-1])[::-1]
        near[start:end] = (seg_s - behind <= extra) | (ahead - seg_s <= extra)
    return near
