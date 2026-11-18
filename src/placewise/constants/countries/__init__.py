"""Countries and the places within them that location search reads.

- `countries`: every ISO 3166-1 country (alpha-2, alpha-3, numeric, English name, aliases).
- `usa`, `can`, `ind`, `gbr` (ISO alpha-3, lower case): per-country `country` details and
  `subregions` (admin1); `cities` there are GENERATED from GeoNames by packbuild.cities.
- `regions`: metro and vernacular regions, GENERATED from datasets/regions by packbuild.regions.
- `city_aliases`: other names of cities (and former names of countries), GENERATED from
  datasets/names/aliases.json by packbuild.cities.
- `groups`: country groups (continents, UN M49 regions, business regions, unions, treaties ...)
  with dated memberships, GENERATED from datasets/country_groups by packbuild.country_groups.
- `currency_codes`: the ISO 4217 code per country, GENERATED from CLDR by packbuild.currency_codes.
  Every other country fact (capital, languages, conventions ...) is in the world pack's
  country_facts layer, read by `placewise.world.profile`.
- `ambiguous`: names several places share; `conventions`: how location strings write countries.
"""

from . import ambiguous, can, city_aliases, conventions, currency_codes, gbr, ind, regions, usa
from ._records import Candidate, CityAlias, Metro, NameClash
from .countries import BY_ALPHA2, BY_ALPHA3, BY_NAME, BY_NUMERIC, COUNTRIES, Country, lookup

# alpha-2 -> that country's subregions module (SUBREGIONS, BY_CODE, BY_NAME, lookup)
SUBREGIONS = {"US": usa.subregions, "CA": can.subregions, "IN": ind.subregions, "GB": gbr.subregions}
# every metro and vernacular region
METROS = regions.REGIONS
# other names of cities that no region covers
CITY_ALIASES = city_aliases.CITY_ALIASES
# alpha-2 -> generated cities (name, admin1, population) of the countries with an admin1 table
CITIES = {"US": usa.cities.CITIES, "CA": can.cities.CITIES, "IN": ind.cities.CITIES, "GB": gbr.cities.CITIES}

__all__ = [
    "BY_ALPHA2",
    "BY_ALPHA3",
    "BY_NAME",
    "BY_NUMERIC",
    "CITIES",
    "CITY_ALIASES",
    "COUNTRIES",
    "METROS",
    "SUBREGIONS",
    "Candidate",
    "CityAlias",
    "Country",
    "Metro",
    "NameClash",
    "ambiguous",
    "can",
    "city_aliases",
    "conventions",
    "currency_codes",
    "gbr",
    "ind",
    "lookup",
    "regions",
    "usa",
]
