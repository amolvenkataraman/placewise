"""Canada: country-level details. Its provinces and territories are in `subregions`.

Codes and names come from the ISO 3166-1 table in `countries.countries`; the currency is ISO 4217.
"""

import re

from ..countries import BY_ALPHA2

COUNTRY = BY_ALPHA2["CA"]
ALPHA2 = COUNTRY.alpha2
ALPHA3 = COUNTRY.alpha3
NUMERIC = COUNTRY.numeric
NAME = COUNTRY.name
OFFICIAL_NAME = "Canada"
ALIASES = COUNTRY.aliases
CURRENCY = "CAD"
SUBREGION_KIND = "province"  # what its admin1 is called
# postal code A1A 1A1 (Canada Post: no D, F, I, O, Q or U; no W or Z first)
POSTAL_CODE = re.compile(r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d\b")

# How free text words the country
TEXT_FORMS = ("Canada", "CAN")
