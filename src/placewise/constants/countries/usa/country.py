"""United States: country-level details. Its states, DC and territories are in `subregions`.

Codes and names come from the ISO 3166-1 table in `countries.countries`; the currency is ISO 4217.
"""

import re

from ..countries import BY_ALPHA2

COUNTRY = BY_ALPHA2["US"]
ALPHA2 = COUNTRY.alpha2
ALPHA3 = COUNTRY.alpha3
NUMERIC = COUNTRY.numeric
NAME = COUNTRY.name
OFFICIAL_NAME = "United States of America"
ALIASES = COUNTRY.aliases
CURRENCY = "USD"
SUBREGION_KIND = "state"  # what its admin1 is called
# ZIP or ZIP+4 (USPS)
POSTAL_CODE = re.compile(r"\b\d{5}(?:-\d{4})?\b")

# How free text words the country
TEXT_FORMS = ("US", "USA", "United States", "United States of America")
