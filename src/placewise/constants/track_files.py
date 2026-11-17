"""Signatures and conventions for recognising track files by their content."""

# FIT: a 12- or 14-byte header whose bytes 8-11 are the ASCII ".FIT" data type
FIT_MAGIC = b".FIT"
FIT_MAGIC_OFFSET = 8
# every zip (so every KMZ) starts with a local file header signature
ZIP_MAGIC = b"PK\x03\x04"
# XML root element (local name) of each XML track format
XML_ROOTS = {"gpx": "gpx", "TrainingCenterDatabase": "tcx", "kml": "kml"}
# a unix time above this is milliseconds: 1e11 s is the year 5138, 1e11 ms is March 1973
UNIX_MILLISECONDS_ABOVE = 1e11

# GeoJSON track conventions. Per-point times sit in a coordTimes property (togeojson, Strava, Mapbox) or
# in coordinateProperties (togeojson's newer output); other per-point arrays sit in coordinateProperties.
GEOJSON_TIME_KEYS = ("coordTimes", "times")
GEOJSON_ACTIVITY_KEYS = ("activity", "type", "sport")
GEOJSON_COORDINATE_PROPERTY_COLUMNS = {
    "heart": "hr",
    "heartRate": "hr",
    "heartRates": "hr",
    "cad": "cadence",
    "cads": "cadence",
    "cadences": "cadence",
    "powers": "power",
    "watts": "power",
    "atemp": "temperature",
    "atemps": "temperature",
    "speeds": "speed",
}

# CSV header names by Track column, after normalising: lower case, units in () or [] dropped, spaces
# and hyphens as underscores. The first matching header wins.
CSV_HEADER_ALIASES = {
    "time": ("time", "timestamp", "date_time", "datetime", "time_utc", "utc", "gps_time", "date"),
    "lat": ("lat", "latitude", "lat_deg"),
    "lon": ("lon", "lng", "long", "longitude", "lon_deg"),
    "ele": ("ele", "elevation", "alt", "altitude", "height"),
    "accuracy": ("accuracy", "horizontal_accuracy", "hacc", "h_acc"),
    "speed": ("speed", "velocity"),
    "heading": ("heading", "course", "bearing", "direction"),
    "hr": ("hr", "heart_rate", "heartrate", "bpm"),
    "cadence": ("cadence", "cad"),
    "power": ("power", "watts"),
    "temperature": ("temperature", "temp", "atemp"),
    "satellites": ("satellites", "sats", "num_sats", "satellites_used"),
}
CSV_SEGMENT_HEADERS = ("segment", "segment_index", "track_seg_id")
CSV_DELIMITERS = (",", ";", "\t", "|")
