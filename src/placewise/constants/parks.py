"""Parks and protected areas (placewise.engine._within, packbuild.parks, docs/parks.md)."""

# the packs that carry parks; the default Geocoder opens them when they are installed
PACKS = ("usa-parks", "can-parks", "world-parks")

# polygon layers whose name starts with this are park outlines (parks_national, parks_state ...);
# the point layer of parks known only by a point and an approximate radius
POLYGON_PREFIX = "parks"
POINTS = "park_points"

# tiers (Place.tier): how significant a park is, which sets how far "near" it reaches
NATIONAL = 1  # national parks, preserves, seashores, urban national parks, tiger reserves
STATE = 2  # state / provincial / territorial parks, national forests, wildlife refuges and sanctuaries
REGIONAL = 3  # conservation and recreation areas, reserves, small federal sites
LOCAL = 4  # city and county parks: named only when the point is inside
TIERS = (NATIONAL, STATE, REGIONAL, LOCAL)
# NearSettings field for each tier's "near" distance; LOCAL has none (inside only)
NEAR_SETTING = {NATIONAL: "park_tier1", STATE: "park_tier2", REGIONAL: "park_tier3"}

# a park known only by a point: its radius is that of a circle of its area, capped, because a
# circle is a poor stand-in for a large irregular park (the build applies the cap)
POINT_RADIUS_CAP_KM = 30.0
POINT_NEIGHBOURS = 8  # point parks considered per query point

MAX_NEAR = 3  # parks listed in Result.near per point, after the notable cities
