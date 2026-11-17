"""Whole tracks as routes.

- combine: concat, merge (recordings from several devices), split, crop and reverse;
- compare: Hausdorff and Fréchet distances, corridor overlap ("same route?") and deviations from a
  reference route.
"""

from .combine import concat, crop, merge, reverse, split
from .compare import Deviation, Overlap, deviations, frechet_km, hausdorff_km, overlap, same_route

__all__ = [
    "Deviation",
    "Overlap",
    "concat",
    "crop",
    "deviations",
    "frechet_km",
    "hausdorff_km",
    "merge",
    "overlap",
    "reverse",
    "same_route",
    "split",
]
