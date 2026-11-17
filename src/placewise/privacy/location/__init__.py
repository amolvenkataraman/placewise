"""Location transforms: Tracks or points in, the same out, with positions cut back or blurred. Every
random step is keyed (see placewise.privacy).

- zones: apply_zones, cut around sensitive places at a secret extra distance along the path;
- trim: trim_ends, drop each recording's ends by a fixed plus a secret per-track distance;
- snap: keyed_snap, snap points to a grid with a secret origin;
- noise: geo_indistinguishable, planar Laplace noise, the same for the same place.
"""

from .noise import geo_indistinguishable, radius_quantile
from .snap import keyed_snap
from .trim import trim_ends, trim_jitter_m
from .zones import apply_zones, zone_extra_m

__all__ = [
    "apply_zones",
    "geo_indistinguishable",
    "keyed_snap",
    "radius_quantile",
    "trim_ends",
    "trim_jitter_m",
    "zone_extra_m",
]
