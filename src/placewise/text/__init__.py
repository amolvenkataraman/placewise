"""Free-text locations as listings, profiles and forms write them: "Hybrid - Toronto, ON",
"Remote (Canada)", "SF Bay Area or NYC". Read them with `parse_location`, then filter with the
helpers in `match`. No data packs needed; plug a gazetteer in to confirm city names."""

from .currency import currency_for
from .match import Decision, LocationFilter, in_country, in_region, is_remote_ok_for
from .parse import Gazetteer, LocationPart, ParsedLocation, parse_address, parse_location, readings
from .work_mode import detect_work_mode, structured_work_mode

__all__ = [
    "Decision",
    "Gazetteer",
    "LocationFilter",
    "LocationPart",
    "ParsedLocation",
    "currency_for",
    "detect_work_mode",
    "in_country",
    "in_region",
    "is_remote_ok_for",
    "parse_address",
    "parse_location",
    "readings",
    "structured_work_mode",
]
