"""What the traveller was doing, from a track.

- visits: stays (stops at one place) and the trips between them;
- modes: travel_mode of every step, mode_runs and flights.

Track times must be non-decreasing.
"""

from .modes import Flight, ModeRun, flights, mode_runs, travel_mode
from .visits import Stay, Trip, stays, trips

__all__ = ["Flight", "ModeRun", "Stay", "Trip", "flights", "mode_runs", "stays", "travel_mode", "trips"]
