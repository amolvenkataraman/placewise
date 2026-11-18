"""Notable places: landmarks, universities, stations, stadiums, museums ... (packbuild.notable,
placewise.engine._notable)."""

# the pack and its one point layer; the default Geocoder opens the pack when it is installed
PACK = "world-notable"
LAYER = "notable"

# the layer's `kind` values and the PlaceKind each is reported as (Place.codes["kind"] keeps the
# finer one: a stadium is a building whose kind code says "stadium")
KINDS = {
    "airport": "airport",
    "station": "station",
    "university": "university",
    "campus": "university",
    "stadium": "building",
    "museum": "building",
    "religious_site": "building",
    "bridge": "landmark",
    "park": "park",
    "beach": "beach",
    "landmark": "landmark",
    "viewpoint": "viewpoint",
    "building": "building",
}

# Result.near: notable places listed after the cities and parks, at most MAX_NEAR, each only within
# the distance its fame reaches (fame is a percentile within its kind, 0..1): the best known reach
# far ("near the CN Tower" from Union Station), the rest only next door
MAX_NEAR = 3
NEAR_KM_BY_FAME = ((0.99, 2.0), (0.9, 1.0), (0.0, 0.3))  # (lowest fame, km), farthest first
NEIGHBOURS = 8  # candidates read per query point and fame band
# kinds never listed in `near`: the airport has its own field (Result.airport)
NOT_NEAR = frozenset({"airport"})
