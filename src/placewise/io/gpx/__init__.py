"""GPX 1.0 / 1.1 tracks, routes and waypoints in and out, streamed through expat with no element tree.

Reading:

- namespaces are ignored (GPX 1.0, 1.1 and namespace-less files read alike); extension elements
  are matched by local name, so Garmin TrackPointExtension v1 and v2, Garmin PowerExtension and
  the bare `<power>` some apps write all land in the same columns;
- `<time>` is ISO 8601 (Z, numeric offsets, any number of fractional digits); a time without a
  zone is UTC, as the GPX schema defines. A point without a time, or with an unreadable one, gets
  NaN, so a track recorded without a clock has an all-NaN `time` column;
- `<hdop>` is a unitless dilution of precision, not metres, so it never fills `accuracy`. It is
  returned beside the tracks in `GpxFile.track_hdop` / `route_hdop`; multiply by the receiver's
  error (UERE, a few metres for phones) for a rough accuracy if one is needed;
- points whose lat/lon are missing, out of range, not plain decimals (xsd:decimal has no exponent,
  so "1.2E-5" is a logger bug) or exactly 0,0 (a receiver without a fix) are dropped and counted
  in `GpxFile.skipped`. A segment left empty by this disappears;
- `meta.activity` is the track's `<type>`, else an `Activity = ...` comment as BasicAirData GPS
  Logger writes, else the file's `<metadata><keywords>`. `meta.name` falls back to the file's
  `<metadata><name>`; `meta.device` is the `creator` attribute.

Writing produces GPX 1.1: speed, course, hr, cadence and temperature go in Garmin
TrackPointExtension v2, power in Garmin PowerExtension, accuracy (metres) in a placewise extension.
hr, cadence and satellites are integers in their schemas and are rounded.
"""

from .reader import GpxFile, Waypoint, read_gpx
from .writer import write_gpx

__all__ = ["GpxFile", "Waypoint", "read_gpx", "write_gpx"]
