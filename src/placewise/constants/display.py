"""How Results and Entities show to people: the text card (`print(result)`) and the notebook table
(placewise.model.display)."""

WIDTH = 100  # widest a text card gets, columns
INDENT = "  "  # before each field line
GAP = 2  # spaces between a value and its right-aligned source, at least
MIN_VALUE = 24  # narrower than this, a line drops its source to keep the value readable
ELLIPSIS = "…"
SEPARATOR = " · "  # between the places of one line (within, near, regions)
DECIMALS = 5  # coordinates: about a metre
NEAR_SHOWN = 3  # places of Result.near on the card, nearest first
ALIASES_SHOWN = 5
ALTERNATES_SHOWN = 3

# the field lines of a Result's card, in order; empty fields have none
RESULT_FIELDS = (
    "sublocality", "locality", "city", "borough", "admin2", "admin1", "country", "postal", "regions",
    "within", "water", "airport", "near", "relative", "tz", "disputed",
)  # fmt: skip
# the lines of an Entity's card
ENTITY_FIELDS = ("kind", "point", "extent", "id", "score", "codes", "aliases", "alternates")
# Place.codes an Entity's card leaves out: the context line says them already
ENTITY_HIDDEN_CODES = ("iso2", "admin1")

# a Nearby at this distance or less with one of these relations reads "on Lake Tahoe", "at SFO"
HERE_KM = 0.05
HERE_RELATIONS = ("on", "over", "at", "within")
SHORE_RELATIONS = ("on", "over")  # water the point is on: its distance is to the shore, not to it
NOT_INSIDE = (
    "not inside"  # a field filled by a fallback (Result.matches): "Lake Louise · 3.1 km away, not inside"
)
IN_AREA = "in the area of"  # a point park's circle holds the point: near at 0 km

# ANSI styles, used only when writing to a terminal (https://no-color.org: NO_COLOR turns them off)
NO_COLOR_ENV = "NO_COLOR"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
KEY = "\x1b[36m"  # cyan field names
RESET = "\x1b[0m"
