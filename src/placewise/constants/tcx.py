"""Garmin Training Center XML (TCX) v2:
https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd
"""

TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
# Speed (m/s), Watts and RunCadence live in this extension, in a <TPX> under each Trackpoint's <Extensions>
ACTIVITY_EXTENSION_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = f"{TCX_NS} http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
ROOT_ELEMENT = "TrainingCenterDatabase"
# the schema's Sport_t enumeration; anything else must be written as Other
SPORTS = ("Running", "Biking", "Other")
DEFAULT_SPORT = "Other"
# HeartRateBpm and Cadence are xsd:unsignedByte with these bounds in the schema
HEART_RATE_RANGE = (1, 255)
CADENCE_RANGE = (0, 254)
