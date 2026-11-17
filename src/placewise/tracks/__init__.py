"""Tracks: the columnar Track model and what you can do with one.

- clean: sort, dedupe, drop invalid points, remove spikes, split gaps, smooth, thin;
- measure: stats, splits, best efforts, grade, heart-rate zones;
- interpolate: position at any time, photo geotagging, camera clock offsets, resampling;
- segment: stays, trips, travel modes, flights;
- spatial: time inside an area, border crossings, closest pass, bounding box, days in each country;
- combine: concat, merge recordings from several devices, split, crop, reverse;
- compare: Hausdorff and Fréchet distances, corridor overlap ("same route?"), deviations from a route.

Track has thin methods for the common operations (`track.clean()`, `track.stats()` ...).
"""

from . import clean, combine, compare, interpolate, measure, segment, spatial
from .combine import concat, crop, merge, reverse, split
from .compare import Deviation, Overlap, deviations, frechet_km, hausdorff_km, overlap, same_route
from .interpolate import ClockOffset, Geotags, estimate_clock_offset, geotag, position_at, resample
from .measure import BestEffort, HrZone, Split, TrackStats, best_efforts, grade, hr_zones, pace, splits, stats
from .segment import Flight, ModeRun, Stay, Trip, flights, mode_runs, stays, travel_mode, trips
from .spatial import ClosestPass, Crossing, bbox, closest_pass, crossings, presence_days, time_inside
from .track import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, Track, TrackMeta

__all__ = [
    "OPTIONAL_COLUMNS",
    "REQUIRED_COLUMNS",
    "BestEffort",
    "ClockOffset",
    "ClosestPass",
    "Crossing",
    "Deviation",
    "Flight",
    "Geotags",
    "HrZone",
    "ModeRun",
    "Overlap",
    "Split",
    "Stay",
    "Track",
    "TrackMeta",
    "TrackStats",
    "Trip",
    "bbox",
    "best_efforts",
    "clean",
    "closest_pass",
    "combine",
    "compare",
    "concat",
    "crop",
    "crossings",
    "deviations",
    "estimate_clock_offset",
    "flights",
    "frechet_km",
    "geotag",
    "grade",
    "hausdorff_km",
    "hr_zones",
    "interpolate",
    "measure",
    "merge",
    "mode_runs",
    "overlap",
    "pace",
    "position_at",
    "presence_days",
    "resample",
    "reverse",
    "same_route",
    "segment",
    "spatial",
    "split",
    "splits",
    "stats",
    "stays",
    "time_inside",
    "travel_mode",
    "trips",
]
