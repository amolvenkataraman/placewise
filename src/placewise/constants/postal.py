"""World postcodes: the optional `world-postal` pack (packbuild.postal) and how lookup reads it
(placewise.engine._postal, docs/postal.md). GeoNames' postal codes are points, not areas, so a
lookup only ever says a point is *near* a postcode."""

# the optional pack and its one point layer; the default Geocoder opens the pack when installed
PACK = "world-postal"
LAYER = "postal"
NEAREST = "nearest"  # rule name in Result.sources ("world-postal/postal:nearest")

# Countries left out of the pack, and why. Better postal data: the country packs carry postal
# areas (US ZIP Code areas, Canadian forward sortation areas, Indian PIN areas).
BETTER_ELSEWHERE = {
    "US": "usa-zip: ZIP Code Tabulation Areas",
    "CA": "can: forward sortation areas",
    "IN": "ind: PIN code areas",
}
# Files GeoNames publishes without a documented source, or codes no postal service uses
LEFT_OUT = {
    "SG": "source undocumented (the design page skips Singapore)",
    "PT": "source undocumented",
    "AE": "the UAE has no postcode system; the source of its 178,000 codes is undocumented",
    "HK": "Hong Kong has no postcodes (999077 is a placeholder)",
    "MO": "Macau has no postcodes (999078 is a placeholder)",
}
# Codes left out by prefix: Northern Ireland's (BT) fall under Land and Property Services' terms
# (internal business use only), not the Royal Mail licence of the rest of the UK file
LEFT_OUT_PREFIXES = {"GB": ("BT",)}
# business-mail codes (France's CEDEX and its overseas departments'): an address, not a place
BUSINESS_CODE_WORDS = ("CEDEX",)
# countries whose rows without an accuracy are large recipients' own codes, named after the
# organisation ("10099 Humboldt-Universität"): Germany's 8,242 such rows; its delivery codes all
# have one
BUSINESS_ROWS_WITHOUT_ACCURACY = frozenset({"DE"})

# A coordinate shared by this many different codes of one country is a placeholder (Paris's
# centre, given to every arrondissement code beside its own point): a code's row there is dropped
# when the code has a point of its own elsewhere
PLACEHOLDER_CODES = 3

# How far a postcode point answers a lookup: per country, REACH_FACTOR times the REACH_PERCENTILE
# of the distances between its points and their nearest neighbours, within REACH_MIN_KM ..
# REACH_MAX_KM (dense Dutch PC4 points reach a few km, Chinese prefecture codes 30 km). A country
# with one code (a small territory) answers anywhere in it.
REACH_PERCENTILE = 90
REACH_FACTOR = 2.0
REACH_MIN_KM = 2.0
REACH_MAX_KM = 30.0
NEIGHBOURS = 8  # candidates read per point: the nearest of its own country within reach wins

# the id of a postcode point: "postal:FR:75007", then ":2", ":3" ... for the code's other points
# (a code covering several places has a point at each)
ID_PREFIX = "postal"
