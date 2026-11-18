"""Forward search (placewise.search): how a query is read, how candidates are ranked and merged."""

# -- reading the query ------------------------------------------------------------------------------

# words a name may carry that the data leaves off ("Peel Region" is the census division "Peel"):
# tried without them when the whole name matches nothing exactly
GENERIC_SUFFIXES = ("regional municipality", "region", "municipality", "district", "city")
GENERIC_PREFIXES = ("city of", "town of", "region of", "municipality of")
# a query this short or shorter without a space may be a code (YYZ, M5V, CA-ON, 94105, Q1049470)
CODE_MAX_CHARS = 16
# placewise ids look like "<scheme>:<value>" ("census:0646870", "iso:IN-KA", "wikidata:Q1049470")
ID_SEPARATOR = ":"
# the id scheme of an Entity built for coordinates typed as text (RFC 5870 geo URI)
GEO_SCHEME = "geo"

# -- gathering candidates ---------------------------------------------------------------------------

CANDIDATES_PER_PACK = 200  # prefix and fuzzy candidates asked of each pack's name index
# fuzzy matches are gathered too when the best exact match's prior is below this (a typo of a big
# place can beat a tiny place spelled exactly like the typo)
FUZZY_BELOW_PRIOR = 0.35
POOL_FACTOR = 4  # candidates ranked and deduplicated per result asked for

# -- ranking: score = match ** MATCH_POWER x prior term x context ---------------------------------

MATCH_POWER = 3.0  # how hard an inexact match is punished against an exact one
PRIOR_FLOOR = 0.15  # the prior term is PRIOR_FLOOR + (1 - PRIOR_FLOOR) x rank, so rank 0 still counts
FUZZY_FACTOR = 0.85  # a fuzzy match's score is further multiplied by this
# name kinds (official, alias, former, code, abbreviation): how much each is worth as a match
NAME_KIND_FACTOR = {"official": 1.0, "alias": 0.97, "former": 0.95, "abbreviation": 0.95, "code": 1.0}
CONTEXT_MISS_FACTOR = 0.2  # a candidate outside the "Name, Context" context, when nothing is inside
CONTEXT_LATER_READING = 0.9  # inside the context's second (or later) reading ("CA" as Canada)
CITY_ALIAS_FACTOR = 0.98  # a match through a city alias ("Bombay" -> Mumbai) from location search
NEAR_SCALE_KM = 250.0  # near=(lat, lon): the boost halves about every 0.7 x this many km
NEAR_FLOOR = 0.25  # ... down to this factor far away
OVERRIDE_BOOST = 2.0  # entities an alias, rename, region or add rule names for the text

# -- merging the same place found in several packs -------------------------------------------------

DEDUPE_POINT_KM = 15.0  # two point features with the same name this close are one place
# kinds that may describe one real place under one name (Toronto the city, its census
# subdivision, its census division and its metro area), and how strongly each is preferred as the
# answer the others are listed under
SETTLEMENT_PREFERENCE = {"locality": 4, "borough": 3, "sublocality": 3, "admin2": 2, "region": 1}

# -- Entities ---------------------------------------------------------------------------------------

# radius (km) of a point feature without one of its own, by kind
POINT_RADIUS_KM = {"locality": 5.0, "airport": 2.0, "sublocality": 1.5, "park": 1.0}
DEFAULT_POINT_RADIUS_KM = 0.5
# layer columns copied into Place.codes when present
CODE_COLUMNS = (
    "iata",
    "icao",
    "iso2",
    "iso3",
    "usps",
    "code",
    "pincode",
    "pcode",
    "wikidata",
    "state_code",
)
REVERSE_CACHE_SIZE = 4096  # Entity contexts (city, region, country) kept per worldview
