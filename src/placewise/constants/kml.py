"""KML 2.2 (OGC 07-147r2) and Google's gx extensions: https://developers.google.com/kml/documentation/kmlreference"""

KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
ROOT_ELEMENT = "kml"
# a KMZ is a zip whose main document is conventionally doc.kml; older tools use any one .kml at the top
KMZ_MAIN_DOCUMENT = "doc.kml"
# gx:SimpleArrayData names that devices and converters (Garmin, Google, GPSBabel) use, by Track column
SIMPLE_ARRAY_COLUMNS = {
    "heartrate": "hr",
    "heart_rate": "hr",
    "hr": "hr",
    "cadence": "cadence",
    "cad": "cadence",
    "power": "power",
    "watts": "power",
    "speed": "speed",
    "temperature": "temperature",
    "temp": "temperature",
}
