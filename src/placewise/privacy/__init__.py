"""Location privacy: hide or blur what tracks and points reveal before you share them.

Tracks in, Tracks out; points in, points out. Every randomised step is keyed: pass the same secret
`key` (bytes, at least 16; e.g. os.urandom(32), stored and reused) and the same input always gives
the same output, so re-sharing never leaks more, and without the key the offsets can't be guessed.

- zones.apply_zones: cut around sensitive places, at a secret extra distance along the path;
- trim.trim_ends: drop each recording's ends, by a fixed plus a secret per-track distance;
- snap.keyed_snap: snap points to a grid with a secret origin;
- noise.geo_indistinguishable: planar Laplace noise, the same for the same place;
- time.coarsen_times / time.shift_times: coarser or shifted timestamps;
- audit.audit: what an observer could infer (home, work, repeated endpoints);
- policies.apply and presets.preset: run a PrivacyPolicy's steps in a fixed order.

Each module's docstring says what it protects against and what it doesn't.
"""

from . import audit, noise, policies, presets, snap, time, trim, zones
from .audit import AuditReport, Finding
from .noise import geo_indistinguishable, radius_quantile
from .policies import apply
from .presets import preset
from .snap import keyed_snap
from .time import coarsen_times, shift_times
from .trim import trim_ends, trim_jitter_m
from .zones import apply_zones, zone_extra_m

__all__ = [
    "AuditReport",
    "Finding",
    "apply",
    "apply_zones",
    "audit",
    "coarsen_times",
    "geo_indistinguishable",
    "keyed_snap",
    "noise",
    "policies",
    "preset",
    "presets",
    "radius_quantile",
    "shift_times",
    "snap",
    "time",
    "trim",
    "trim_ends",
    "trim_jitter_m",
    "zone_extra_m",
    "zones",
]
