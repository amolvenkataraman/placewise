"""Encoded polylines (Google's Encoded Polyline Algorithm Format):
https://developers.google.com/maps/documentation/utilities/polylinealgorithm
"""

# Google Maps uses 5 decimal places (about 1 m); OSRM and Valhalla can use 6 (about 0.1 m)
DEFAULT_PRECISION = 5
CHUNK_BITS = 5
CHUNK_MASK = (1 << CHUNK_BITS) - 1
CONTINUATION_BIT = 1 << CHUNK_BITS  # set on every chunk but a value's last
# added to each 6-bit chunk so the output is printable ASCII, "?" (63) through "~" (126)
CHAR_OFFSET = 63
