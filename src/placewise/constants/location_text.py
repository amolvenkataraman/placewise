"""The vocabulary of free-text locations: separators, noise words, placeholders and list markers.

They were collected from real-world location strings (listings, profiles, forms); the forms
they cover are documented in docs/text-parsing.md. Words are matched whole and
case-insensitively; a space in a phrase also matches a hyphen or no space ("north east" matches
"Northeast" and "north-east").
"""

# characters read as a plain hyphen or a plain space
DASHES = "‐‑‒–—―−﹘﹣－"
SPACES = "     \t\r\f\v"

# between places: "Toronto, ON; Vancouver, BC", "A | B", "A • B", one per line
PLACE_SEPARATORS = (";", "|", "\n", "•", "·")
# between alternatives inside one place-list: "US or Canada", "US and Canada", "US & Canada", "US/Canada"
ALTERNATIVE_WORDS = ("or", "and")

# dropped from a part: "Toronto Office", "San Francisco HQ", "Greater Boston Area", "Downtown Toronto"
NOISE_WORDS = (
    "office", "offices", "hq", "headquarters", "area", "greater", "metro", "metropolitan", "downtown",
    "campus", "region", "only", "based", "located", "work", "main", "location", "locations", "site",
)  # fmt: skip
# directions and coasts that name no place: "Northeast - United States"
DIRECTIONS = (
    "north east", "north west", "south east", "south west", "mid west", "west coast", "east coast",
    "pacific northwest",
)  # fmt: skip

# text no city is called: a site, a building, a street address; with digits, always
NOT_A_CITY_WORDS = (
    "building", "bldg", "tower", "floor", "suite", "ste", "fab", "complex", "facility", "facilities", "zone",
    "factory", "home", "offsite", "warehouse", "street", "road", "avenue", "blvd", "pkwy", "hwy", "multiple",
    "various",
)  # fmt: skip
# placeholders that name nothing
PLACEHOLDERS = ("tbd", "tba", "n/a", "unspecified", "not specified")

# words before a place that aren't part of it: "Remote in USA", "Based in Toronto", "within the US"
LEADING_WORDS = (
    "based in", "located in", "in", "at", "from", "within", "across", "throughout", "near", "only",
)  # fmt: skip

# "Multiple Locations", "Various locations", "3 Locations"; "+ 6 others", "and 2 more" are fixed forms
LIST_MARKER_WORDS = ("multiple", "various", "several", "many", "numerous")
LIST_MORE_WORDS = ("others", "other", "more")

# names containing "and" that aren't two places, beyond the reference tables' names
AND_NAMES = ("Australia and New Zealand", "Europe, Middle East and Africa", "Latin America and the Caribbean")

# structured address keys: JSON-LD PostalAddress and the plain city / state / stateCode / country /
# countryCode keys common in feeds
ADDRESS_KEYS = (
    ("addressLocality", "locality", "city", "town", "name"),
    ("addressRegion", "region", "state", "stateCode", "province", "admin1"),
    ("addressCountry", "country", "countryCode", "country_code"),
)

# Country groups location search reads as a remote-work limit ("Remote - EMEA"), by id in
# constants.countries.groups (from datasets/country_groups); their names and aliases are what it
# matches. Other groups ("US & Canada", "NATO") are left out on purpose: "US & Canada" reads as
# the two countries. The world group means no limit.
REMOTE_SCOPE_GROUPS = (
    "geo:world", "geo:north-america", "geo:us-canada-mexico", "geo:namer", "geo:m49-americas",
    "geo:latam", "geo:latin-america-caribbean", "geo:europe", "legal:eu", "geo:emea", "geo:middle-east",
    "geo:mena", "geo:africa", "geo:apac", "geo:dach", "geo:nordic", "geo:benelux", "geo:anz",
)  # fmt: skip
WORLDWIDE_GROUP = "geo:world"

# Cities taken as a currency hint when no country can be found ("Toronto" -> CAD)
CURRENCY_CITY_HINTS = {"Toronto": "CAD", "Vancouver": "CAD", "London": "GBP", "Berlin": "EUR", "Paris": "EUR"}
