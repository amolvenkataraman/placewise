"""Read a free-text location ("Hybrid - Toronto, ON or Remote (Canada)") into places, a work mode and
the countries a remote listing is limited to. See docs/text-parsing.md for the forms it reads.

How a string is read:

1. Work-mode phrases ("Remote", "Hybrid", "On-site", "in office 3 days/week") and list markers
   ("Multiple locations", "+ 6 others") are found and blanked out, so offsets into `raw` survive.
2. ";", "|", "•" and new lines separate places. Inside each, " or ", " and ", "&" and "/" separate
   places too, except inside names that contain them ("Trinidad and Tobago", "Newfoundland and
   Labrador") and inside parentheses.
3. Each place is split into parts on "," and " - " (and "-" or "." between codes: "US-CA-Menlo
   Park", "US.AZ.Tempe"), and a trailing or leading code is peeled off "Austin TX". A list that
   starts with its region or country ("US, CA, Santa Clara", "California - San Francisco") is
   reversed. Noise words (Office, HQ, Area, Greater, Metro, Downtown ...) are dropped.
4. Parts are grouped into places: a city, then its admin1 and country. A second city, or a region
   that can't belong with the ones before it, starts the next place ("Toronto, ON, Vancouver, BC").
5. Each place's codes and names are read against the reference tables (constants.countries: the
   ISO list, the usa, can, ind and gbr subregions, regions, city aliases and known cities); every consistent
   reading is a candidate, the likeliest first, the rest kept as `alternatives`.

Ambiguity rules:

- A two-letter code counts only as a whole part: after a comma, a dash or a parenthesis, or peeled
  off "City ST" when written in capitals. "ON" and "IN" inside prose ("work in office on Fridays")
  are words, never Ontario or Indiana.
- A code that is a state, a province and a country reads in that order:
  "Smallville, CA" is California with Canada as the alternative; "Amsterdam, NL" is the
  Netherlands with Newfoundland and Labrador as the alternative. Another part settles it
  ("Kitchener, ON, CA"), as do `context`, a city a metro lists ("Mumbai, MH") and the gazetteer.
- Indian state codes (KA, MH, TN ...) count only with India in the string, an Indian `context`, or
  a city a metro lists in that state; full names (Karnataka) always count.
- A remote listing's lone two-letter code prefers its country reading: "CA-Remote" is Canada.
- A region name followed by a state or province is a city: "Ontario, CA" is Ontario, California;
  "Washington, DC" is the city; "Ontario, Canada" is the province.
- "Georgia" is the US state with a US city or a US context (given, or set by the other places in
  the string), the country with one of its cities (Tbilisi ...), and ambiguous (0.5 / 0.5) alone.
- Bare city names that several well-known cities share ("London", "Cambridge", "Vancouver") come
  back with every candidate and a confidence each (constants.countries.ambiguous); context reorders them.
- Without a gazetteer, any other bare city keeps no country and confidence 0.5.

The gazetteer hook: pass any object with `.match(city, country_iso2, admin1_code) -> Place | None`.
Candidates it confirms win (and are marked `city_verified`); a bare city gets its country and
admin1 from the Place's `codes["iso2"]` and `codes["admin1"]`.

Modules: `model` (the types), `patterns` (compiled vocabularies), `readings` (what a code or name
means), `spans` (offsets and splitting), `tokenize` (one place-string into parts), `group` (parts
into places), `resolve` (one place's candidates), `modes` (work-mode phrases), `api` (entry points).
"""

from placewise.constants.work_modes import HYBRID, MODES, ONSITE, REMOTE

from .api import parse_address, parse_location
from .model import Gazetteer, LocationPart, ParsedLocation
from .readings import readings

WORK_MODES = MODES

__all__ = [
    "HYBRID",
    "ONSITE",
    "REMOTE",
    "WORK_MODES",
    "Gazetteer",
    "LocationPart",
    "ParsedLocation",
    "parse_address",
    "parse_location",
    "readings",
]
