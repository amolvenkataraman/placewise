"""Naming rules (placewise.engine.naming, docs/naming.md): which country-pack layers name a point
and the distances and sizes the rules use. Thresholds are starting points, to tune against a
labelled set of public places (tests/e2e)."""

# layers the naming rules read from country packs (packbuild/README.md)
REGIONS = "regions"  # curated region polygons, in any country pack: id, name, kind, country
USA_LAYERS = {
    "county": "counties", "place": "places", "postal": "zcta", "cbsa": "cbsa", "csa": "csa",
    "postal_cities": "postal_cities",
}  # fmt: skip
USA_STATES, CAN_PROVINCES = "states", "provinces"  # admin-1 layers (their time zones, engine._timezones)
# the optional pack holding the US ZIP Code areas (`zcta`); without it the usa pack's `postal_cities`
# (the ZIP Codes' postal cities where they can name a locality) still corrects the locality
USA_ZIP_PACK = "usa-zip"
CAN_LAYERS = {
    "division": "cd", "subdivision": "csd", "metro": "cma", "postal": "fsa", "named": "populated_places",
}  # fmt: skip
IND_LAYERS = {
    "postal": "pincodes", "state": "states", "district": "districts", "city": "cities",
    "neighbourhood": "neighbourhoods",
}  # fmt: skip
# the India pack's id suffix for the part of a unit only India's view puts in India (a district
# reaching into Gilgit-Baltistan has "lgd:district:9" and "lgd:district:9#india-view")
IND_VIEW_ONLY_SUFFIX = "#india-view"
# India: a point in a city takes as sublocality the nearest neighbourhood (a post office's name) of
# that city within this distance, looking at this many nearest points; city post offices are
# about 1-2 km apart
IND_NEIGHBOURHOOD_KM = 1.5
IND_NEIGHBOURHOOD_CANDIDATES = 8
# installed packs the default Geocoder opens beside "world" (alpha-3 names, and the older alpha-2)
COUNTRY_PACKS = ("usa", "us", USA_ZIP_PACK, "can", "ca", "ind", "in")

# rule names in Result.sources ("us/places:metro")
METRO = "metro"  # the metro area's principal city (US) or first city (Canada) stands for the point
POSTAL = "postal"  # the ZIP Code's postal city stands for a CDP or unincorporated land (US)
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

# Canada's named places (CGNDB populated places, can/populated_places). A rural or unorganised
# subdivision is named first by the nearest settlement inside it within CGNDB_LOCALITY_KM (Lake
# Louise, 0.2 km from its hamlet point and 2.7 km from it at the lake), then by GeoNames
CGNDB_LOCALITY_KM = 4.0
CGNDB_LOCALITY_TERMS = frozenset(
    {
        "Hamlet", "Community", "Compact Rural Community", "Dispersed Rural Community", "Rural Community",
        "Settlement", "Organized Hamlet", "Northern Hamlet", "Northern Community", "Northern Settlement",
        "Northern Village", "Suburban Community", "Village", "Town", "City", "Rural Village",
        "Resort Village", "Summer Village", "Police Village", "Local Urban District",
        "Recreational Community",
        "Resort", "Resort Area", "Townsite", "Metis Settlement", "First Nation Village", "Cree Village",
        "Naskapi Village", "Amerindian Settlement", "Charter Community", "Forest Village",
    }
)  # fmt: skip
# a subdivision named as itself (a city, a township) takes as sublocality the neighbourhood or
# community inside it whose reach the point is deepest inside; the reach grows with the name's
# "Relevance at Scale" (shown from 1:700,000 and up: Scarborough, Kanata, Etobicoke), as
# (scale at least, km), largest first. Railway points, localities without people and dispersed
# rural communities never name a sublocality
CGNDB_SUBLOCALITY_KM = ((700_000, 4.0), (250_000, 2.5), (0, 1.5))
CGNDB_SUBLOCALITY_TERMS = frozenset(
    {
        "Urban Community", "Neighbourhood", "Community", "Suburban Community", "Residential Area", "Borough",
        "Administrative Sector", "Subdivision", "Village", "Town", "Hamlet", "Compact Rural Community",
    }
)  # fmt: skip
CGNDB_CANDIDATES = 8  # nearest named points looked at per query point

# city roll-up (design page "Three names per point"): a locality stays the city when it has
# CITY_KEEP_POPULATION people or is named in its metro's title; otherwise the metro's first city
# stands for it when that city is CITY_ROLL_UP_RATIO times bigger (Pickering -> Toronto)
CITY_KEEP_POPULATION = 100_000
CITY_ROLL_UP_RATIO = 10

# US postal city: inside a metro area, a census-designated place (CDP) or unincorporated land takes
# the city its ZIP Code's addresses name (Paradise -> Las Vegas, SFO -> San Francisco) when that
# city's boundary is this close; farther off, a ZIP Code's name is a post office, not a place
POSTAL_CITY_KM = 20.0
# a CDP this populous keeps its own name when its postal city is just another CDP (The Woodlands,
# addressed Spring); a smaller one takes it. An incorporated postal city wins regardless (design:
# "CDP of 5,000+ people stays", unless the postal city says otherwise)
CDP_KEEP_POPULATION = 5_000
# unincorporated land with no postal city takes its metro's largest principal city (OMB list 2)
# when that city's boundary is this close
METRO_CITY_KM = 25.0

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
