"""Tracks: the columnar Track model and what you can do with one.

- track: the Track container (columns, segments, metadata);
- cleaning: sort, dedupe, drop invalid points, remove spikes, split gaps, smooth, thin;
- metrics: stats, splits, best efforts, grade, heart-rate zones;
- timing: position at any time, photo geotagging, camera clock offsets, resampling;
- movement: stays, trips, travel modes, flights;
- areas: time inside an area, border crossings, closest pass, bounding box, days in each country;
- routes: concat, merge recordings from several devices, split, crop, reverse; Hausdorff and
  Fréchet distances, corridor overlap ("same route?"), deviations from a route.

Track has thin methods for the common operations (`track.clean()`, `track.stats()` ...).
"""

from . import areas, cleaning, metrics, movement, routes, timing
from .areas import ClosestPass, Crossing, bbox, closest_pass, crossings, presence_days, time_inside
from .metrics import BestEffort, HrZone, Split, TrackStats, best_efforts, grade, hr_zones, pace, splits, stats
from .movement import Flight, ModeRun, Stay, Trip, flights, mode_runs, stays, travel_mode, trips
from .routes import (
    Deviation,
    Overlap,
    combine,
    compare,
    concat,
    crop,
    deviations,
    frechet_km,
    hausdorff_km,
    merge,
    overlap,
    reverse,
    same_route,
    split,
)
from .timing import ClockOffset, Geotags, estimate_clock_offset, geotag, position_at, resample
from .track import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, Track, TrackMeta

# The modules of the first, flat layout, as aliases of what replaced them, so that
# `placewise.tracks.clean.smooth`, `placewise.tracks.measure.stats` and the like keep working.
clean = cleaning
interpolate = timing
measure = metrics
segment = movement
spatial = areas

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
    "areas",
    "bbox",
    "best_efforts",
    "clean",
    "cleaning",
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
    "metrics",
    "mode_runs",
    "movement",
    "overlap",
    "pace",
    "position_at",
    "presence_days",
    "resample",
    "reverse",
    "routes",
    "same_route",
    "segment",
    "spatial",
    "split",
    "splits",
    "stats",
    "stays",
    "time_inside",
    "timing",
    "travel_mode",
    "trips",
]
