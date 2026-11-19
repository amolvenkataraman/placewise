"""Forward search (placewise.search): how a query is read, how candidates are ranked and merged."""

# -- reading the query ------------------------------------------------------------------------------

# words a name may carry that the data leaves off ("Peel Region" is the census division "Peel"):
# tried without them when the whole name matches nothing exactly
GENERIC_SUFFIXES = ("regional municipality", "region", "municipality", "district", "city")
GENERIC_PREFIXES = ("city of", "town of", "region of", "municipality of")
# a query this short or shorter without a space may be a code (YYZ, M5V, CA-ON, 94105, Q1049470)
CODE_MAX_CHARS = 16
# a two-part postcode whose first part has no digit has at most this many letters ("AZ 0100")
SPACED_CODE_LETTERS = 3
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
PREFIX_FLOOR = 0.6  # a prefix match's term: PREFIX_FLOOR + (1 - PREFIX_FLOOR) x the share typed
# prefix candidates asked of each pack when a spatial filter (within=, bbox=, near= with
# radius_km=) will drop most of them ("Lake" within the Bay Area)
PREFIX_FILTERED_LIMIT = 20_000
FUZZY_FACTOR = 0.85  # a fuzzy match's score is further multiplied by this
# name kinds (official, alias, former, code, abbreviation): how much each is worth as a match
NAME_KIND_FACTOR = {"official": 1.0, "alias": 0.97, "former": 0.95, "abbreviation": 0.95, "code": 1.0}
CONTEXT_MISS_FACTOR = 0.2  # a candidate outside the "Name, Context" context, when nothing is inside
CONTEXT_LATER_READING = 0.9  # inside the context's second (or later) reading ("CA" as Canada)
CITY_ALIAS_FACTOR = 0.98  # a match through a city alias ("Bombay" -> Mumbai) from location search
NEAR_SCALE_KM = 250.0  # near=(lat, lon): the boost halves about every 0.7 x this many km
NEAR_FLOOR = 0.25  # ... down to this factor far away
OVERRIDE_BOOST = 2.0  # entities an alias, rename, region or add rule names for the text

# -- what is named after a place -------------------------------------------------------------------

# a station, airport, university, building or landmark called Richmond, a park known as Boise, a
# code that reads like a word ("Goa" is Genoa's airport code) are rarely what someone typing the
# name means when a place of that name also matches: they score SHADOW_FACTOR times as much
SHADOWING_KINDS = ("country", "admin1", "admin2", "locality", "borough", "sublocality", "region")
FACILITY_KINDS = ("airport", "station", "university", "building", "landmark")
SHADOW_MIN_RANK = 0.3  # ... a place this prominent or more (a hamlet called Times Square isn't)
SHADOW_FACTOR = 0.7
SHADOW_CANDIDATES = 64  # the best this many candidates are compared by name
# while typing (prefix matches), people mostly want places: FACILITY_KINDS score this much less
TYPING_FACILITY_FACTOR = 0.85
# a code that is a postal code means the postal area ("10001"): other code matches score at most
# this times the best postal code match
CODE_AFTER_POSTAL = 0.99
# "Mississippi River" is also looked up as "Mississippi" among waters (Natural Earth's river names
# leave the word off), worth an alias
WATER_WORDS = ("river",)
WATER_WORD_FACTOR = 0.97

# -- merging the same place found in several packs -------------------------------------------------

DEDUPE_POINT_KM = 15.0  # two point features with the same name this close are one place
# a park point (world-parks: Wikidata's coordinate, often a rough one) with an outline park's name
# within this distance of the outline's box is that park (Swiss National Park's point is 0.5 km
# outside its outline)
DEDUPE_PARK_KM = 5.0
PARK_KIND = "park"
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
    "wikidata",
    "state_code",
)
REVERSE_CACHE_SIZE = 4096  # Entity contexts (city, region, country) kept per worldview
# Entity.context_certain is False within this of another country's or region's outline: the
# world pack's Natural Earth 1:10m borders: catches 90-99% of the points a 1:10m admin1 polygon
# gets wrong in the US, Canada and India, flagging 2-9% of points (docs/search.md, "How sure the
# context is")
CONTEXT_BORDER_KM = 5.0

# kinds= accepts these everyday words for PlaceKind values
KIND_ALIASES = {
    "city": "locality",
    "town": "locality",
    "village": "locality",
    "municipality": "locality",
    "neighbourhood": "sublocality",
    "neighborhood": "sublocality",
    "state": "admin1",
    "province": "admin1",
    "county": "admin2",
    "district": "admin2",
    "metro": "region",
    "postal": "postal_code",
    "postcode": "postal_code",
    "zip": "postal_code",
    "lake": "water",
    "river": "water",
    "sea": "water",
    "ocean": "water",
    "university": "university",
    "mountain": "peak",
}

# which context an Entity carries, by its kind's level: country (level >= 1), region (>= 2),
# city (>= 4); a country carries only its own code, a state its country, a city its state too
CONTEXT_LEVEL = {
    "country": 0,
    "admin1": 1,
    "admin2": 2,
    "region": 2,
    "park": 2,
    "water": 2,
    "island": 2,
    "peak": 2,
    "trail": 2,
    "highway": 2,
    "ski_area": 2,
    "timezone": 1,
    "locality": 3,
}
CONTEXT_LEVEL_DEFAULT = 4  # neighbourhoods, postal codes, airports, landmarks ... carry a city

# -- codes mean what people mean ------------------------------------------------------------------

AIRPORT_WORDS = ("airport", "airports", "intl", "international")  # "YYZ airport" means the airport
SERVED_CITY_KM = 60.0  # an airport serves the largest city this close in its country ...
SERVED_COLUMN = "served"  # ... unless the airports layer names it (a city id) in this column
SERVED_CITY_FACTOR = 1.05  # the served city scores this much above its airport
SERVED_CITY_D0_KM = 2.0  # served city fit: population / (km + this)
AIRPORT_AFTER_CITY = 0.999  # the airport scores this much below the city it serves
# a country code that is also an airport code ("BLR": Belarus and Bengaluru's airport) means the
# airport's city, unless the country is commonly written by it (constants.countries.conventions
# ALPHA3_ANY_CASE: "IND" is India, "CAN" Canada)
COUNTRY_CODE_BELOW_AIRPORT = 0.99
