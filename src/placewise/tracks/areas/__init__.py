"""A track against places.

- inside: time_inside an area, crossings between areas;
- extent: closest_pass to a point, the track's bbox;
- presence: presence_days, days present per country or region.

Track times must be non-decreasing.
"""

from .extent import ClosestPass, bbox, closest_pass
from .inside import Crossing, crossings, time_inside
from .presence import presence_days

__all__ = ["ClosestPass", "Crossing", "bbox", "closest_pass", "crossings", "presence_days", "time_inside"]
