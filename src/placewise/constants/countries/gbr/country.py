"""United Kingdom: country-level details. Its countries (England, Scotland, Wales, Northern
Ireland) are in `subregions`.

Codes and names come from the ISO 3166-1 table in `countries.countries`.
"""

import re

from ..countries import BY_ALPHA2

COUNTRY = BY_ALPHA2["GB"]
ALPHA2 = COUNTRY.alpha2
ALPHA3 = COUNTRY.alpha3
NUMERIC = COUNTRY.numeric
NAME = COUNTRY.name
OFFICIAL_NAME = "United Kingdom of Great Britain and Northern Ireland"
ALIASES = COUNTRY.aliases
SUBREGION_KIND = "country"  # what its admin1 is called
# postcode (Royal Mail outward and inward codes)
POSTAL_CODE = re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?|GIR) ?\d[A-Z]{2}\b")
