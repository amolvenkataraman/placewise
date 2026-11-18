"""Which layers of each pack the name index covers, and how (packbuild.names.LayerNames).

Ranks land on one scale across packs, so the query engine can compare them: countries 0.85-1,
first-level divisions ~0.75-0.85, a 3M city ~0.8, a 100k town ~0.55, a hamlet ~0.2, national
parks ~0.8, metro regions ~0.75, postal codes 0.2, a pocket park ~0.1.
"""

from placewise.constants.codab import COUNTRIES, LAYER_PREFIX

from .names import LayerNames, Rank, Term

# populated places by population: 300 people -> base, 20M -> base + span
_PEOPLE = {"column": "population", "lo": 2.5, "hi": 7.3}
_CITY = Rank(base=0.1, span=0.85, **_PEOPLE)
_ALIASES = ("aliases",)
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
        aliases=_ALIASES,
        codes=("iso2", "iso3"),
        id_codes=("iso:",),
        rank=Rank(base=0.85, span=0.15, column="population", lo=4, hi=9),
    ),
    LayerNames(
        "admin1",
        "admin1",
        aliases=("name_alt", "aliases"),
        id_codes=("iso:",),
        rank=Rank(base=0.75),
    ),
    LayerNames("cities", "locality", names=("name", "asciiname"), aliases=_ALIASES, rank=_CITY),
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
    LayerNames("counties", "admin2", rank=Rank(base=0.5)),
    LayerNames("places", "locality", rank=_CITY, point=("intpt_lat", "intpt_lon")),
    LayerNames("cbsa", "region", names=("name", "title"), codes=("code",), rank=Rank(base=0.55)),
    LayerNames("csa", "region", names=("name", "title"), codes=("code",), rank=Rank(base=0.55)),
    LayerNames(
        "zcta", "postal_code", names=(), codes=("name",), rank=_POSTAL, point=("intpt_lat", "intpt_lon")
    ),
    _REGIONS,
)

CAN = (
    LayerNames(
        "provinces",
        "admin1",
        aliases=("name_fr",),
        codes=("code", "CA-{code}"),
        rank=Rank(base=0.75, span=0.1, column="population", lo=4.5, hi=7.2),
    ),
    LayerNames("cd", "admin2", rank=Rank(base=0.45, span=0.25, column="population", lo=3, hi=6.5)),
    LayerNames("csd", "locality", rank=_CITY),
    LayerNames(
        "cma",
        "region",
        aliases=("name_full",),
        codes=("cmauid",),
        rank=Rank(base=0.5, span=0.35, column="population", lo=4, hi=7),
    ),
    LayerNames("fsa", "postal_code", names=(), codes=("name",), rank=_POSTAL),
    LayerNames("populated_places", "locality", rank=Rank(base=0.15)),
    _REGIONS,
)

# India Post office names end in the office type: "Koramangala S.O", "Kotuvalli SO"
_OFFICE_SUFFIXES = tuple(
    f" {s}" for s in ("S.O", "B.O", "H.O", "G.P.O", "GPO", "SO", "BO", "HO", "PO", "S.O.", "B.O.", "H.O.")
)

IND = (
    LayerNames("pincodes", "postal_code", names=(), codes=("pincode",), rank=_POSTAL),
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
    LayerNames(
        "lakes",
        "water",
        aliases=_ALIASES,
        codes=("wikidata",),
        rank=Rank(base=0.25, span=0.55, column="area_km2", lo=0, hi=5),
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


def codab(country):
    """Specs for a COD-AB pack: ADM1 is admin1; the levels placewise.constants.codab names
    admin2, locality and sublocality are those kinds; other levels are administrative (admin2)."""
    specs = []
    for level in range(1, country.levels + 1):
        if level == 1:
            kind, rank = "admin1", 0.72
        elif level == country.locality:
            kind, rank = "locality", 0.35
        elif level == country.sublocality:
            kind, rank = "sublocality", 0.2
        else:
            kind, rank = "admin2", 0.45 if level == country.admin2 else 0.35
        specs.append(LayerNames(f"{LAYER_PREFIX}{level}", kind, codes=("pcode",), rank=Rank(base=rank)))
    return tuple(specs)


SPECS = {
    "world": WORLD,
    "usa": USA,
    "can": CAN,
    "ind": IND,
    "world-water": WATER,
    "parks": PARKS,  # usa-parks, can-parks, world-parks
    **{iso3: codab(country) for iso3, country in COUNTRIES.items()},  # COD-AB packs
}
