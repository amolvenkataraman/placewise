"""GPX namespaces and the element names that map onto Track columns."""

GPX_10_NS = "http://www.topografix.com/GPX/1/0"
GPX_11_NS = "http://www.topografix.com/GPX/1/1"
GPX_11_XSD = "http://www.topografix.com/GPX/1/1/gpx.xsd"

GARMIN_TPX_V1_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
GARMIN_TPX_V2_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v2"
GARMIN_TPX_V2_XSD = "http://www.garmin.com/xmlschemas/TrackPointExtensionv2.xsd"
GARMIN_POWER_NS = "http://www.garmin.com/xmlschemas/PowerExtension/v1"
GARMIN_POWER_XSD = "http://www.garmin.com/xmlschemas/PowerExtensionv1.xsd"
# no public schema carries a metres-valued horizontal accuracy, so placewise writes its own
PLACEWISE_NS = "urn:placewise:gpx:1"

# direct children of <trkpt>/<rtept>; speed and course exist only in GPX 1.0, sat and hdop in both
POINT_ELEMENTS = {
    "ele": "ele",
    "speed": "speed",
    "course": "heading",
    "sat": "satellites",
    "hdop": "hdop",  # unitless dilution of precision, kept out of `accuracy` (metres)
}

# local names inside <extensions>, whatever their namespace: Garmin TrackPointExtension v1/v2
# (hr, cad, atemp, speed, course), Garmin PowerExtension (PowerInWatts), the bare <power> that
# Strava and others write, and the metres-valued accuracy used by OpenTracks and placewise
EXTENSION_ELEMENTS = {
    "hr": "hr",
    "heartrate": "hr",
    "cad": "cadence",
    "cadence": "cadence",
    "atemp": "temperature",
    "temp": "temperature",
    "speed": "speed",
    "course": "heading",
    "power": "power",
    "PowerInWatts": "power",
    "accuracy": "accuracy",
    "accuracy_horizontal": "accuracy",
}
