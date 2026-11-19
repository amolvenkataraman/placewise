"""Which layers of each pack the name index covers, and how (packbuild.names.LayerNames).

Ranks land on one scale across packs, so the query engine can compare them: countries 0.85-1,
first-level divisions ~0.5-0.85 (by population), a 3M city ~0.8, a 100k town ~0.55, a hamlet ~0.2, national
parks ~0.8, metro regions ~0.75, postal codes 0.2, a pocket park ~0.1.
"""

from placewise.constants import notable

from .names import LayerNames, Rank, Term

# populated places by population: 300 people -> base, 20M -> base + span
_PEOPLE = {"column": "population", "lo": 2.5, "hi": 7.3}
_CITY = Rank(base=0.1, span=0.85, **_PEOPLE)
_ALIASES = ("aliases",)
_WORLD_ALIASES = ("aliases", "abbreviations")  # packbuild.world_aliases
_FORMER = ("former_names",)
# counties and census divisions by population: 1,000 people -> base, 3M -> base + span
_COUNTY = Rank(base=0.45, span=0.25, column="population", lo=3, hi=6.5)
_COMMUNITIES = (
    "Community",
    "Urban Community",
    "Suburban Community",
    "Neighbourhood",
    "Administrative Sector",
)
_CGNDB = Rank(
    base=0.15,
    terms=(
        Term("scale", 0.2, lo=5.2, hi=6.1),
        Term("generic", 0.15, scale="values", values=dict.fromkeys(_COMMUNITIES, 1.0)),
    ),
)
_REGION = Rank(base=0.72, terms=(Term("area_km2", 0.1, lo=3, hi=5),))
_POSTAL = Rank(base=0.2, terms=(Term("population", 0.05, lo=2, hi=5),))
_PARK = Rank(
    base=0.1,
    terms=(Term("tier", 0.45, lo=1, hi=4, scale="invert"), Term("area_km2", 0.35, lo=-1, hi=4)),
)

WORLD = (
    LayerNames(
        "countries",
        "country",
        aliases=_WORLD_ALIASES,
        former=_FORMER,
        codes=("iso2", "iso3"),
        id_codes=("iso:",),
        rank=Rank(base=0.85, span=0.15, column="population", lo=4, hi=9),
    ),
    LayerNames(
        "admin1",
        "admin1",
        aliases=("name_alt", *_WORLD_ALIASES),
        former=_FORMER,
        id_codes=("iso:",),
        # by the people of its cities (packbuild.world.admin1_population): 100k -> base, 100M ->
        # base + span, so a city outranks the same-named unit around it unless that is far bigger
        rank=Rank(base=0.5, span=0.3, column="population", lo=5, hi=8),
    ),
    LayerNames(
        "cities",
        "locality",
        names=("name", "asciiname"),
        aliases=_WORLD_ALIASES,
        former=_FORMER,
        codes=("airport_codes",),  # YYZ finds Toronto, the city the airport serves
        rank=_CITY,
    ),
    LayerNames(
        "airports",
        "airport",
        codes=("iata", "icao"),
        rank=Rank(
            base=0.35,
            terms=(
                Term("type", 0.4, scale="values", values={"large_airport": 1.0, "medium_airport": 0.5}),
                Term("scheduled", 0.05, scale="linear", lo=0, hi=1),
            ),
        ),
    ),
)

_REGIONS = LayerNames("regions", "region", aliases=("short_name", "aliases"), rank=_REGION)

USA = (
    LayerNames("states", "admin1", codes=("usps",), id_codes=("iso:",), rank=Rank(base=0.8)),
    LayerNames("counties", "admin2", rank=_COUNTY),
    LayerNames("places", "locality", rank=_CITY, point=("intpt_lat", "intpt_lon")),
    LayerNames("cbsa", "region", names=("name", "title"), codes=("code",), rank=Rank(base=0.55)),
    LayerNames("csa", "region", names=("name", "title"), codes=("code",), rank=Rank(base=0.55)),
    _REGIONS,
)

USA_ZIP = (
    LayerNames(
        "zcta", "postal_code", names=(), codes=("name",), rank=_POSTAL, point=("intpt_lat", "intpt_lon")
    ),
)

# GeoNames postcode points (packbuild.postal): each code once, on its first point; found by the
# code as written and without spaces or hyphens ("100 00", "10000"); place names are not indexed
WORLD_POSTAL = (
    LayerNames("postal", "postal_code", names=(), codes=("codes",), skip="secondary", rank=_POSTAL),
)

CAN = (
    LayerNames(
        "provinces",
        "admin1",
        aliases=("name_fr",),
        codes=("code", "CA-{code}"),
        rank=Rank(base=0.75, span=0.1, column="population", lo=4.5, hi=7.2),
    ),
    LayerNames("cd", "admin2", rank=_COUNTY),
    LayerNames("csd", "locality", rank=_CITY),
    LayerNames(
        "cma",
        "region",
        aliases=("name_full",),
        codes=("cmauid",),
        rank=Rank(base=0.5, span=0.35, column="population", lo=4, hi=7),
    ),
    LayerNames("fsa", "postal_code", names=(), codes=("name",), rank=_POSTAL),
    # by the map scale CGNDB shows each at (relevance at scale: 1:160,000 -> 0, 1:1.25M and up -> full)
    # and its kind (a community or neighbourhood, not a locality: sparse maps show remote localities
    # at small scales too), so Scarborough (a community inside Toronto at 1:1.2M) ranks like a town
    # and a hamlet stays near the base; no city ranks above its census subdivision's population
    LayerNames("populated_places", "locality", rank=_CGNDB),
    _REGIONS,
)

# India Post office names end in the office type: "Koramangala S.O", "Kotuvalli SO"
_OFFICE_SUFFIXES = tuple(
    f" {s}" for s in ("S.O", "B.O", "H.O", "G.P.O", "GPO", "SO", "BO", "HO", "PO", "S.O.", "B.O.", "H.O.")
)

_VIEW_ONLY = "india_view_only"  # a unit's piece only India's view puts in India: indexed once

IND = (
    LayerNames("states", "admin1", aliases=_ALIASES, codes=("iso",), skip=_VIEW_ONLY, rank=Rank(base=0.8)),
    LayerNames("districts", "admin2", aliases=_ALIASES, skip=_VIEW_ONLY, rank=Rank(base=0.5)),
    LayerNames(
        "cities",
        "locality",
        aliases=("aliases", "official_name"),
        skip=_VIEW_ONLY,
        rank=Rank(base=0.45, span=0.4, column="area_km2", lo=0.5, hi=2.9),  # 3 -> 800 km2
    ),
    LayerNames("neighbourhoods", "sublocality", rank=Rank(base=0.2)),
    LayerNames("pincodes", "postal_code", names=(), codes=("pincode",), skip=_VIEW_ONLY, rank=_POSTAL),
    LayerNames("post_offices", "sublocality", strip_suffixes=_OFFICE_SUFFIXES, rank=Rank(base=0.12)),
    _REGIONS,
)

WATER = (
    LayerNames(
        "marine",
        "water",
        aliases=_ALIASES,
        codes=("wikidata",),
        rank=Rank(base=0.4, span=0.55, column="area_km2", lo=2, hi=8),
    ),
    *(
        LayerNames(
            layer,
            "water",
            aliases=_ALIASES,
            codes=("wikidata",),
            rank=Rank(base=0.25, span=0.55, column="area_km2", lo=0, hi=5),
        )
        for layer in ("lakes", "reservoirs")  # Global Dam Watch reservoirs rank like lakes
    ),
    LayerNames(
        "rivers",
        "water",
        aliases=_ALIASES,
        codes=("wikidata",),
        rank=Rank(base=0.3, span=0.5, column="scalerank", lo=0, hi=12, invert=True),
    ),
)

PARKS = (
    *(
        LayerNames(layer, "park", aliases=_ALIASES, codes=("code",), rank=_PARK)
        for layer in ("parks_national", "parks_state", "parks_regional", "parks_local")
    ),
    LayerNames(
        "park_points",
        "park",
        aliases=_ALIASES,
        codes=("wikidata",),
        rank=Rank(
            base=0.1,
            terms=(Term("tier", 0.45, lo=1, hi=4, scale="invert"), Term("sitelinks", 0.35, lo=0, hi=2)),
        ),
    ),
)


# famous places (packbuild.notable): the kind per row; fame (a percentile within the kind) below
# 0.5 adds nothing, the best known land with national parks and 3M cities
NOTABLE = (
    LayerNames(
        notable.LAYER,
        "landmark",
        aliases=_ALIASES,
        codes=("iata", "icao", "station_code"),
        id_codes=("wikidata:",),  # the bare QID
        kind_column="kind",
        kind_values=notable.KINDS,
        rank=Rank(base=0.15, terms=(Term("fame", 0.7, lo=0.5, hi=1.0, scale="linear"),)),
    ),
)

SPECS = {
    "world": WORLD,
    "usa": USA,
    "usa-zip": USA_ZIP,
    "world-postal": WORLD_POSTAL,
    "can": CAN,
    "ind": IND,
    "world-water": WATER,
    "parks": PARKS,  # usa-parks, can-parks, world-parks
    "world-notable": NOTABLE,
}
