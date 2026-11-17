"""File formats in and out: polygons (GeoJSON, shapefiles) and tracks (GPX, FIT, TCX, KML, GeoJSON, NMEA, CSV).

`read_track` detects the format from the content and dispatches to the right reader."""

from ._track_common import TrackReadWarning
from .csv_tracks import read_csv_track, write_csv_track
from .detect import detect_format, read_track
from .fit import FitDevice, FitError, FitFile, FitLap, FitSession, read_fit
from .geojson import read_geojson
from .geojson_tracks import read_geojson_tracks, write_geojson_track
from .gpx import GpxFile, Waypoint, read_gpx, write_gpx
from .kml import read_kml
from .nmea import read_nmea
from .shapefile import read_shapefile
from .tcx import read_tcx, write_tcx

__all__ = [
    "FitDevice",
    "FitError",
    "FitFile",
    "FitLap",
    "FitSession",
    "GpxFile",
    "TrackReadWarning",
    "Waypoint",
    "detect_format",
    "read_csv_track",
    "read_fit",
    "read_geojson",
    "read_geojson_tracks",
    "read_gpx",
    "read_kml",
    "read_nmea",
    "read_shapefile",
    "read_tcx",
    "read_track",
    "write_csv_track",
    "write_geojson_track",
    "write_gpx",
    "write_tcx",
]
