"""Water: the `world-water` pack's layers and how lookup uses them (placewise.engine._water,
docs/water.md). Distances are starting points, to tune against public places (tests/e2e)."""

# the optional pack the default Geocoder opens beside "world" when it is installed
PACK = "world-water"
# its layers (packbuild/README.md, "Water pack"); any pack carrying them is read
MARINE = "marine"  # seas, oceans, gulfs, bays, straits: Natural Earth marine polygons
LAKES = "lakes"  # lakes and reservoirs: HydroLAKES, Natural Earth
RESERVOIRS = "reservoirs"  # Global Dam Watch reservoirs no named lake covers; read like lakes
RIVERS = "rivers"  # river centerlines, stored as zero-area polygons (each line out and back)
LAYERS = (MARINE, LAKES, RESERVOIRS, RIVERS)
LAKE_LAYERS = (LAKES, RESERVOIRS)  # on or near a lake: lakes first, so a lake answers before a reservoir

# the `type` column: what the feature is (Place.codes["type"])
OCEAN, SEA, LAKE, RESERVOIR, RIVER = "ocean", "sea", "lake", "reservoir", "river"

# rule names in Result.sources ("world-water/marine:polygon")
POLYGON = "polygon"  # the point is inside the water body
NEAREST = "nearest"  # in no sea polygon, but this one's edge is within MARINE_SNAP_KM

# On water. A point is on a sea when it is in no country polygon and at least this far from the
# nearest one (Natural Earth's 1:10m coast misses piers, harbours and some city centres by
# hundreds of metres: closer than this it is on land, beside the sea).
SEA_SHORE_MARGIN_KM = 1.0
# ...and on a lake when inside it and at least this far from its shore, per source: HydroLAKES and
# Global Dam Watch (mostly HydroLAKES' and SWBD's outlines) are drawn at 1:100k-1:250k, Natural
# Earth at 1:10m (its lake shores are off by up to ~1 km)
LAKE_SHORE_MARGIN_KM = {"hydrolakes": 0.1, "gdw": 0.1, "naturalearth": 0.5}
LAKE_SHORE_MARGIN_DEFAULT_KM = 0.5
# Natural Earth's marine polygons follow the coast to ~1 km, leaving slivers of sea in none of
# them: a sea point there takes the polygon whose edge is nearest, this close
MARINE_SNAP_KM = 25.0

# Near water, for points on land (or on water within the shore margin)
SEA_NEAR_KM = 5.0  # "by the Arabian Sea": the marine polygon's edge this close
RIVER_NEAR_KM = 2.0  # Natural Earth's river lines are ~1 km from the bank (Ganges at Varanasi)
# a lake is near when its shore is this close, by the lake's area (km²): the Great Lakes are
# landmarks from kilometres away, a pond only from its bank
LAKE_NEAR_KM = ((10_000.0, 5.0), (100.0, 2.0), (10.0, 1.0), (0.0, 0.3))

# Labels: "On Lake Tahoe", "On the North Atlantic Ocean"; "Over Lake Ontario" from a plane
OVER_WORD, ON_WORD = "Over", "On"
# On or over: every water body is ON unless the lookup gives an altitude (`altitude_m`, metres
# above mean sea level; the WGS84 ellipsoid's difference of up to ~100 m is ignored) at least
# OVER_HEIGHT_M above the water's surface: a boat, a ferry or a lakeside hotel's roof stays "On",
# a plane is "Over". Surfaces: seas and oceans SEA_SURFACE_M; lakes HydroLAKES' `Elevation` and
# reservoirs Global Dam Watch's `ELEV_MASL` (the `elevation_m` column, metres above sea level,
# from a 90 m DEM); Natural Earth's lakes, rivers and packs built before the column: unknown.
# Over water of unknown surface only from AIRBORNE_M up: higher than any water on Earth stands
# (the highest lakes are at ~6,000 m) plus OVER_HEIGHT_M, so clearly in flight anywhere.
OVER_HEIGHT_M = 100.0
SEA_SURFACE_M = 0.0
AIRBORNE_M = 9_000.0
ELEVATION = "elevation_m"  # the lakes' and reservoirs' surface column (NaN where unknown)
ELEVATION_NULL_BELOW_M = -1_000.0  # the sources' null (-9999); the Dead Sea is at -430 m
# English names that take "the": by type (oceans, seas, straits, channels, fjords, reefs,
# rivers: "the Kattegat", "the Ganges"), else by the name's form ("the Persian Gulf", "the Bay of
# Bengal", "the Hirakud Reservoir"), but not lakes ("Lake Tahoe"), bays or sounds ("Hudson Bay")
THE_TYPES = frozenset({OCEAN, SEA, "strait", "channel", "fjord", "reef", RIVER, "canal"})
THE_SUFFIXES = (
    " Ocean", " Sea", " Gulf", " Channel", " Strait", " Straits", " Passage", " Bight", " Reef",
    " Reservoir", " River", " Canal", " Lagoon",
)  # fmt: skip
THE_PREFIXES = ("Gulf of ", "Gulf ", "Bay of ", "Sea of ", "Strait of ", "Straits of ", "Bight of ")
THE = "the"

# Sources considered and rejected (docs/water.md). The Marine Regions IHO Sea Areas (v3, 2018)
# are CC BY-NC-SA 4.0 (its download form says so; the design page had it as CC BY): non-commercial,
# so Natural Earth's public-domain marine polygons stand in. HydroRIVERS falls under the HydroSHEDS
# v1 licence (no stand-alone redistribution, a pass-through end-user licence, an indemnity).
REJECTED = {
    "marineregions-iho": "CC-BY-NC-SA-4.0: non-commercial and share-alike",
    "hydrorivers": "HydroSHEDS v1 licence: no stand-alone redistribution",
}

# Build (packbuild.sources.naturalearth_water, hydrolakes): English display names.
# Natural Earth's marine `name_en` (from Wikidata labels) is English but drops the ocean halves
# and has a few surprises; these keep `name` instead (by Wikidata id): Cook Inlet (not "Tikahtnu
# Inlet"), Hangzhou Bay (not "Hangzhouwan"), Garabogaz Bay (not "Garabogazköl")
NE_KEEP_NAME = frozenset({"Q1129590", "Q700024", "Q239379"})
NE_KEEP_NAME_TYPES = frozenset({"ocean", "river"})  # "North Atlantic Ocean", "Amazon River"
# typos and forms fixed wherever a source spells them so
NAME_FIXES = {
    "Hinakud Dam": "Hirakud Reservoir",
    "Banggong Co": "Pangong Tso",
    "Kaliningrad": "Vistula Lagoon",  # Natural Earth names the lagoon after the city
}
# a reservoir named "<X> Dam" is "<X>" when X already names water, else "<X> Reservoir"
WATER_WORDS = (
    "Lake", "Lac", "Lago", "Loch", "Lough", "Reservoir", "Sagar", "Sarovar", "Tal", "Taal", "Jheel",
    "Tso", "Co", "Hu", "Nur", "Nuur", "See", "Sea", "Pond", "Tank", "Water", "Basin",
)  # fmt: skip
# a Global Dam Watch dam name still holding one of these (after its trailing "Dam" is dropped)
# names a structure, not water ("West Forebay Dike GJ-18"): with no reservoir name, it is left out
DAM_STRUCTURE_WORDS = frozenset(
    {
        "dike",
        "dyke",
        "sluice",
        "spillway",
        "weir",
        "levee",
        "embankment",
        "barrage",
        "structure",
        "lock",
        "gate",
    }
)
# a river name with none of these words is a bare name: "Black" -> "Black River"
RIVER_WORDS = (
    "River", "Creek", "Brook", "Canal", "Stream", "Fork", "Run", "Bayou", "Río", "Rio", "Rivière",
    "Fleuve", "Nahr", "Nadi", "Gang", "Wadi",
)  # fmt: skip

# Build defaults (packbuild.water): HydroLAKES lakes of at least this area (km²) are kept, and
# their outlines simplified to this tolerance (metres; the source is 1:100k-1:250k)
MIN_LAKE_KM2 = 10.0
LAKE_TOLERANCE_M = 30.0
# Global Dam Watch reservoirs: the same size threshold; one a named lake covers (at least this
# share of sample points inside it in the lakes layer) is left out, the lake already answering
MIN_RESERVOIR_KM2 = MIN_LAKE_KM2
RESERVOIR_COVERED = 0.5
