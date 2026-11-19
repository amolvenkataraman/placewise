"""Parks and protected areas (placewise.engine._nearby.parks, packbuild.parks, docs/parks.md)."""

# the packs that carry parks; the default Geocoder opens them when they are installed
# usa-parks-local: city and county parks; eur-parks: outlines for Europe (EEA countries), optional
PACKS = ("usa-parks", "usa-parks-local", "can-parks", "eur-parks", "world-parks")

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

# the label rule (docs/naming.md, LabelSettings.parks): a point in a park of tier LABEL_MAX_TIER or
# more significant is labelled "<locality>, <park>" ("Lake Louise, Banff National Park"). Not for
# national forests and grasslands: their administrative boundaries take in whole towns (South Lake
# Tahoe lies in the Lake Tahoe Basin Management Unit), whose people name the town, not the forest.
# Europe's nature parks, biosphere reserves and protected landscapes (eur-parks) are lived-in
# landscapes the same way
LABEL_MAX_TIER = STATE
LABEL_SKIP_DESIGNATIONS = frozenset({
    "National Forest", "National Grassland",
    "Nature Park", "Regional Park", "Landscape Park", "Biosphere Reserve", "Protected Landscape Area",
})  # fmt: skip

# names that say what kind of land a parcel is, not which place it is: never a park's name. PAD-US
# fills its unit name with them ("Unknown Park" 1,869 parcels, "Open Space" 528); the build takes
# the parcel's local name instead or leaves the parcel out (packbuild/sources/parks), and the
# engine and search skip them in packs built before that. Compared case-folded, accents and
# repeated spaces ignored. "City Park", "Central Park" and "Town Forest" are real names: kept
GENERIC_NAMES = frozenset({
    "park", "parks", "unknown", "unknown park", "unnamed", "unnamed park", "no name", "park land",
    "parkland", "open space", "open space area", "municipal open space", "city open space",
    "county open space", "public open space", "common open space", "conservation easement",
    "easement", "conservation area", "conservation land", "natural area", "nature area",
    "nature preserve", "preserve", "greenbelt", "green belt", "greenspace", "green space",
    "greenway", "municipal park", "county park", "state park", "state forest", "recreation area",
    "public land", "public access", "access area", "fishing access", "boat launch", "boat ramp",
    "wildlife area", "wildlife management area", "island", "playground", "tot lot", "pocket park",
    "mini park", "skate park", "dog park", "ball field", "ball fields", "athletic field",
    "athletic fields", "vacant land", "undeveloped land", "unknown open space", "town open space",
    "village open space", "statewide natural area", "statewide wildlife habitat", "local forest",
    "forest", "nf", "wetland", "wetlands", "habitat", "agriculture", "rangeland", "bird sanctuary",
    "state trust land", "state lands", "water district lands", "department of transportation area",
    "nc land and water fund project", "nc land and water fund conservation agreement",
})  # fmt: skip
