"""Apply a PrivacyPolicy to a Track, step by step in a fixed order:

1. zones: cut around each PrivacyZone (zones.apply_zones);
2. trim: drop each segment's ends (trim.trim_ends);
3. snap or noise: keyed grid snapping (snap.keyed_snap) or geo-indistinguishable noise
   (noise.geo_indistinguishable); a policy asking for both is rejected as ambiguous. Either one
   also drops the speed, heading and accuracy columns, which would let dead reckoning rebuild the
   exact path or bound the blur;
4. time: floor times (time.coarsen_times);
5. metadata: with strip_metadata, keep only the activity (name, device and source identify you).

Cutting and trimming run on true positions, so the cuts land where they are meant to; blurring
comes after so it can't move a point back out of a zone before the zone test; times go last
because the trim jitter is seeded by the track's real first timestamp.
"""

from placewise.tracks import TrackMeta

from ._common import check_key, replace_columns
from .noise import geo_indistinguishable
from .snap import keyed_snap
from .time import coarsen_times
from .trim import trim_ends
from .zones import apply_zones

_REVEALING_COLUMNS = ("speed", "heading", "accuracy")


def apply(track, policy, key):
    """A new Track with `policy` applied (see the module docstring for the order)."""
    key = check_key(key)
    if policy.cloak_min_population is not None:
        raise NotImplementedError(
            "cloak_min_population needs population data from placewise's geocoder, which isn't "
            "available yet; it will arrive with the geocoder integration. Use snap_m or "
            "noise_epsilon for now."
        )
    if policy.snap_m is not None and policy.noise_epsilon is not None:
        raise ValueError("a policy can snap (snap_m) or add noise (noise_epsilon), not both")
    if policy.zones:
        track = apply_zones(track, policy.zones, key)
    if policy.trim_m or policy.trim_jitter_m:
        track = trim_ends(track, policy.trim_m, policy.trim_jitter_m, key)
    if policy.snap_m is not None:
        lat, lon = keyed_snap(track.lat, track.lon, policy.snap_m, key)
        track = replace_columns(track, drop=_REVEALING_COLUMNS, lat=lat, lon=lon)
    elif policy.noise_epsilon is not None:
        lat, lon = geo_indistinguishable(track.lat, track.lon, policy.noise_epsilon, key)
        track = replace_columns(track, drop=_REVEALING_COLUMNS, lat=lat, lon=lon)
    if policy.time_resolution is not None:
        track = coarsen_times(track, policy.time_resolution)
    if policy.strip_metadata:
        track = replace_columns(track, meta=TrackMeta(activity=track.meta.activity))
    return track
