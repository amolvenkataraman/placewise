"""Privacy policies: what to hide or blur before sharing locations. Applied by placewise.privacy."""

from dataclasses import dataclass

from ._base import Model, set_field
from .geometry import Point

TIME_RESOLUTIONS = frozenset({"minute", "hour", "day"})


@dataclass(frozen=True, slots=True)
class PrivacyZone(Model):
    name: str
    point: Point
    radius_m: float

    def __post_init__(self):
        if self.radius_m <= 0:
            raise ValueError("zone radius must be positive")


@dataclass(frozen=True, slots=True)
class PrivacyPolicy(Model):
    zones: tuple[PrivacyZone, ...] = ()
    trim_m: float = 0.0  # drop this much from each track's start and end
    trim_jitter_m: float = 0.0  # ... plus a reproducible per-track amount up to this
    cloak_min_population: int | None = None  # generalise to an area holding at least this many people
    snap_m: float | None = None  # keyed grid snapping cell size
    noise_epsilon: float | None = None  # geo-indistinguishability budget per metre
    time_resolution: str | None = None
    strip_metadata: bool = True

    def __post_init__(self):
        set_field(self, "zones", tuple(self.zones))
        if self.trim_m < 0 or self.trim_jitter_m < 0:
            raise ValueError("trim distances can't be negative")
        for name in ("cloak_min_population", "snap_m", "noise_epsilon"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.time_resolution is not None and self.time_resolution not in TIME_RESOLUTIONS:
            raise ValueError(f"time_resolution must be one of {sorted(TIME_RESOLUTIONS)}")
