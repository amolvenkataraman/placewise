"""COD-AB country packs (OCHA Common Operational Datasets, administrative boundaries; packbuild/README.md,
"COD-AB packs"): which countries have one and how their levels name a point (engine/naming/codab.py).

Each pack is named by the country's lower-case ISO 3166-1 alpha-3 code and holds one polygon layer
per administrative level it ships, `admin1`, `admin2`, ... (ADM1, ADM2, ... in COD-AB), ids
`codab:<P-code>`, each row's `parent` the id of the unit one level up.
"""

from typing import NamedTuple

LAYER_PREFIX = "admin"  # layer of ADM level n: f"admin{n}"
ID_PREFIX = "codab:"
# rule name in Result.sources for a level read from the parent of the unit the point is in
PARENT = "parent"


class CodabCountry(NamedTuple):
    """How a COD-AB pack names points in its country. Levels are COD-AB ADM numbers."""

    iso2: str
    levels: int  # the deepest ADM level the pack ships
    admin2: int | None = None  # the level reported as admin2 (district, county), if any
    locality: int | None = None  # the level that is the municipality people name, if any
    sublocality: int | None = None  # a level below the locality that names neighbourhoods
    # whether the world pack's admin1 (Natural Earth) is the same unit as ADM1, so an ADM1 whose name
    # matches a world admin1 of the country keeps the world Place (with its ISO code); otherwise
    # (an older or different level: Sri Lanka's districts, Nepal's pre-2015 zones, Viet Nam's 63
    # pre-2025 provinces, Kenya's former provinces) the ADM1 always answers admin1
    world_admin1: bool = True
    admin1_suffix: str = ""  # appended to ADM1 names: Sri Lanka's "Western" is the Western Province


# Municipal levels: only Nepal's ADM3 (the 753 local levels: metropolitan and sub-metropolitan cities,
# municipalities and rural municipalities) are municipalities named as people name the place. Elsewhere
# the municipal unit is often named otherwise than its town (Mexico's Benito Juarez for Cancun, South
# Africa's Drakenstein for Paarl and City of Tshwane for Pretoria, Bangladesh's "Dhaka South City
# Corporation"), or the level is not municipal (Sri Lanka's divisional secretariats, Thailand's
# amphoe), so the locality stays the GeoNames answer there.
COUNTRIES = {
    "lka": CodabCountry("LK", 4, admin2=2, sublocality=4, world_admin1=False, admin1_suffix=" Province"),
    "npl": CodabCountry("NP", 3, admin2=2, locality=3, world_admin1=False),
    "bgd": CodabCountry("BD", 3, admin2=2),
    "tha": CodabCountry("TH", 3, admin2=2, sublocality=3),
    "vnm": CodabCountry("VN", 1, world_admin1=False),
    "mex": CodabCountry("MX", 2, admin2=2),
    "zaf": CodabCountry("ZA", 3, admin2=2),
    "ken": CodabCountry("KE", 2, admin2=2, world_admin1=False),
    "egy": CodabCountry("EG", 2, admin2=2),
    "tur": CodabCountry("TR", 2, admin2=2),
    "are": CodabCountry("AE", 1),
}
PACKS = tuple(COUNTRIES)
