"""India: country-level details. Its states and union territories are in `subregions`.

Codes and names come from the ISO 3166-1 table in `countries.countries`; the currency is ISO 4217.
"""

import re

from ..countries import BY_ALPHA2

COUNTRY = BY_ALPHA2["IN"]
ALPHA2 = COUNTRY.alpha2
ALPHA3 = COUNTRY.alpha3
NUMERIC = COUNTRY.numeric
NAME = COUNTRY.name
OFFICIAL_NAME = "Republic of India"
ALIASES = COUNTRY.aliases
CURRENCY = "INR"
SUBREGION_KIND = "state"  # what its admin1 is called
# PIN code (India Post: six digits, first not 0)
POSTAL_CODE = re.compile(r"\b[1-9]\d{2}\s?\d{3}\b")
