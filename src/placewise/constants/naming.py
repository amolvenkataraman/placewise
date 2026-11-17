"""Naming rules (placewise.engine.naming, docs/naming.md): which country-pack layers name a point
and the distances and sizes the rules use. Thresholds are starting points, to tune against a
labelled set of public places (tests/e2e)."""

from .codab import PACKS as CODAB_PACKS

# layers the naming rules read from country packs (packbuild/README.md)
REGIONS = "regions"  # curated region polygons, in any country pack: id, name, kind, country
USA_LAYERS = {"county": "counties", "place": "places", "postal": "zcta", "cbsa": "cbsa", "csa": "csa"}
CAN_LAYERS = {"division": "cd", "subdivision": "csd", "metro": "cma", "postal": "fsa"}
IND_LAYERS = {"postal": "pincodes"}
# installed packs the default Geocoder opens beside "world" (alpha-3 names, and the older alpha-2),
# then the COD-AB packs (constants/codab.py)
COUNTRY_PACKS = ("usa", "us", "can", "ca", "ind", "in", *CODAB_PACKS)

# rule names in Result.sources ("us/places:metro")
METRO = "metro"  # the metro area's principal city (US) or first city (Canada) stands for the point
INSIDE = "inside"  # a GeoNames place inside the boundary names a rural or unorganised one
NAME = "name"  # a name derived from the layer's own: the PIN area's post office, NYC's boroughs
STATE = "state"  # admin1 from the state or province a country-pack feature belongs to

# Census and StatCan shapes are clipped to the shoreline, so a pier, a falls or a harbour point can
# miss every one of them; within this distance it takes the nearest (rule "nearest").
SHORE_KM = 1.0

# sublocality: the nearest GeoNames place within this distance that lies in the same locality
# (Mission District in San Francisco, Rouge in Toronto) and isn't named like it
SUBLOCALITY_KM = 2.0
# GeoNames feature codes that are never a sublocality: historical, abandoned, destroyed places
SUBLOCALITY_EXCLUDED_FEATURE_CODES = frozenset({"PPLH", "PPLQ", "PPLW", "PPLCH"})

# a rural or unorganised census subdivision (a township, a rural municipality, an improvement
# district) is named by the nearest GeoNames place inside it, this close
RURAL_PLACE_KM = 8.0

# city roll-up (design page "Three names per point"): a locality stays the city when it has
# CITY_KEEP_POPULATION people or is named in its metro's title; otherwise the metro's first city
# stands for it when that city is CITY_ROLL_UP_RATIO times bigger (Pickering -> Toronto)
CITY_KEEP_POPULATION = 100_000
CITY_ROLL_UP_RATIO = 10

# a US census-designated place or unincorporated land takes its metro's principal city (the first
# one in the CBSA title in the same state) when that city's boundary is this close: the proxy for
# the ZIP Code's postal city (Paradise -> Las Vegas, SFO -> San Francisco) until postal cities are
# in the pack
METRO_CITY_KM = 25.0
# a CDP is that city's suburb only when it is this close to the city (East Los Angeles, Paradise);
# farther out it stays itself (Stanford, Brandon FL)
METRO_CDP_KM = 5.0

# New York City's boroughs are its five counties (county GEOID -> the name people use)
NYC_BOROUGHS = {
    "36005": "Bronx",
    "36047": "Brooklyn",
    "36061": "Manhattan",
    "36081": "Queens",
    "36085": "Staten Island",
}

# StatCan census subdivision types (SGC 2021) by how a point inside them is named. Municipal types
# (cities, towns, villages, municipalities, reserves ...) are the locality themselves.
CSD_RURAL = frozenset(
    {
        "TP",  # township
        "RM",  # rural municipality
        "MD",  # municipal district
        "CT",  # canton (municipalité de)
        "CU",  # cantons unis (municipalité de)
        "P",  # parish
        "PE",  # paroisse (municipalité de)
        "LGD",  # local government district
    }
)
CSD_UNORGANIZED = frozenset(
    {
        "NO",  # unorganized
        "SNO",  # subdivision of unorganized
        "ID",  # improvement district (Alberta's national parks, Kananaskis)
        "SA",  # special area
        "RDA",  # regional district electoral area
        "SC",  # subdivision of county municipality
    }
)

# post-office type words India Post writes after office names ("Whitefield S.O"): sub, branch and
# head office, general post office; a PIN area's name before them names its neighbourhood
OFFICE_SUFFIXES = (
    "S.O.", "B.O.", "H.O.", "S.O", "B.O", "H.O", "SO", "BO", "HO", "PO", "GPO", "G.P.O.", "G.P.O", "HPO",
)  # fmt: skip
