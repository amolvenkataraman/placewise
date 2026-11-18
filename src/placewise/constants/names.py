"""The name index packs carry for forward search (docs/pack-format.md, "Name index")."""

NAMES_DIR = "names"  # reserved layer directory: no layer may be called this
NAMES_JSON = "names.json"
NAMES_FORMAT = 1  # the layout of names/ this code reads and writes
INSIDE_DIR = "inside"  # names/inside/<layer>.npy: a point inside each polygon feature

# what an entry's text is to its feature; an entry's name_kind is its index here
NAME_KINDS = ("official", "alias", "former", "abbreviation", "code")
OFFICIAL, ALIAS, FORMER, ABBREVIATION, CODE = range(len(NAME_KINDS))

# placewise.model.PlaceKind values (tests keep the two in step); an entry's kind is its index here
PLACE_KINDS = (
    "country",
    "admin1",
    "admin2",
    "locality",
    "sublocality",
    "borough",
    "region",
    "postal_code",
    "park",
    "water",
    "airport",
    "university",
    "building",
    "station",
    "peak",
    "island",
    "beach",
    "trail",
    "highway",
    "landmark",
    "ski_area",
    "viewpoint",
    "timezone",
    "custom",
)

# fuzzy matching: keys share padded character trigrams with the query; a key is a candidate when
# it shares at least this fraction of the query's distinct trigrams (and at least one)
FUZZY_MIN_SHARED = 0.4
# ...the best this many candidates by trigram overlap get the edit-distance check
FUZZY_EDIT_POOL = 64
# ...and a key further than this many edits (per character of the longer string) is dropped
FUZZY_MAX_EDIT_RATIO = 0.34

# radius of a point feature without a radius column, from its population (a disc of
# POINT_DENSITY_PER_KM2 people per km², clamped), else POINT_DEFAULT_RADIUS_KM
POINT_DENSITY_PER_KM2 = 2_000.0
POINT_MIN_RADIUS_KM = 0.5
POINT_MAX_RADIUS_KM = 40.0
POINT_DEFAULT_RADIUS_KM = 1.0
