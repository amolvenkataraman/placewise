"""Speed units, as metres per second per unit."""

from .distance import METRES_PER

METRES_PER_SECOND = {
    "m/s": 1.0,
    "km/h": METRES_PER["km"] / 3600,
    "mph": METRES_PER["mi"] / 3600,
    "kn": METRES_PER["nmi"] / 3600,  # knot: one nautical mile per hour
}
