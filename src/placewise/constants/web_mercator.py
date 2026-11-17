"""Web Mercator (EPSG:3857), the projection of OSM-style map tiles."""

import math

# latitude where the projected world becomes a square: atan(sinh(pi)), about 85.0511 degrees
MAX_LAT = math.degrees(math.atan(math.sinh(math.pi)))
