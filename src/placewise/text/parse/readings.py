"""What a code or name can mean: the states, provinces and countries a location part reads as."""

import functools
import re
from dataclasses import dataclass

from placewise.constants import countries
from placewise.constants._keys import key
from placewise.constants.countries import can, gbr, ind, usa
from placewise.constants.countries.ambiguous import AMBIGUOUS_CITIES, NAME_CLASHES
from placewise.constants.countries.conventions import (
    ALPHA3_ANY_CASE,
    LOWERCASE_SHORT_FORMS,
    STATE_CODES_ALSO_COUNTRIES,
)
from placewise.constants.location_text import AND_NAMES

from .. import regions as _regions


@dataclass(frozen=True, slots=True)
class _Reading:
    country: str
    admin1: str | None = None
    by_name: bool = False  # read from a name ("Ontario"), not a code ("ON")
    india_code: bool = False  # an Indian state code, only good with India in sight


def _admin1_name(country, code):
    table = countries.SUBREGIONS.get(country)
    entry = table.BY_CODE.get(code) if table and code else None
    return entry.name if entry else None


@functools.cache
def _readings(text, upper):
    """Every state, province or country `text` can mean, likeliest first. `upper`: written in
    capitals, which three-letter country codes need ("CAN", "SGP")."""
    k = key(text)
    if not k:
        return ()
    found = []
    code = k.upper() if len(k) == 2 and k.isalpha() else None
    if code:
        if code in usa.subregions.BY_CODE:
            found.append(_Reading("US", code))
        is_admin = code in usa.subregions.BY_CODE or code in can.subregions.BY_CODE
        if code in countries.BY_ALPHA2 and (not is_admin or code in STATE_CODES_ALSO_COUNTRIES):
            found.append(_Reading(code))
        if code in can.subregions.BY_CODE:
            found.append(_Reading("CA", code))
    elif len(k) == 3 and k.isalpha():
        three = k.upper()
        if upper and three in gbr.subregions.BY_CODE:  # "ENG"
            found.append(_Reading("GB", three))
        if three in countries.BY_ALPHA3 and (upper or three in ALPHA3_ANY_CASE):
            found.append(_Reading(countries.BY_ALPHA3[three].alpha2))
    if (state := usa.subregions.BY_NAME.get(k)) is not None:
        found.append(_Reading("US", state, by_name=len(k) > 3))
    if (province := can.subregions.BY_NAME.get(k)) is not None:
        found.append(_Reading("CA", province, by_name=len(k) > 3))
    if (state := ind.subregions.BY_NAME.get(k)) is not None and len(k) > 3:
        found.append(_Reading("IN", state, by_name=True))
    if (nation := gbr.subregions.BY_NAME.get(k)) is not None and len(k) > 3:
        found.append(_Reading("GB", nation, by_name=True))
    if (country := countries.BY_NAME.get(k)) is not None and not (len(k) <= 3 and k.isalpha() and not upper):
        found.append(_Reading(country, by_name=len(k) > 3))
    elif country is not None and k in LOWERCASE_SHORT_FORMS:
        found.append(_Reading(country))
    if code and (state := ind.subregions.lookup(code)) is not None:
        found.append(_Reading("IN", state, india_code=True))
    if text.rstrip().endswith(".") and len(k) > 2:  # "Ind." is Indiana's abbreviation, "IND" India
        found.sort(key=lambda r: r.admin1 is None)
    unique = {}
    for reading in found:
        unique.setdefault((reading.country, reading.admin1), reading)
    return tuple(unique.values())


def readings(text):
    """Every state, province or country a location part can mean, likeliest first, as
    (country, admin1) pairs: "CA" -> [("US", "CA"), ("CA", None)]."""
    letters = re.sub(r"[^A-Za-z]", "", text)
    return [(r.country, r.admin1) for r in _readings(text, bool(letters) and letters.isupper())]


def _ambiguous_city(city):
    """The candidates of a bare city name several places share ("London"), or None."""
    k = key(city)
    return next((v for name, v in AMBIGUOUS_CITIES.items() if key(name) == k), None)


def _name_clash(text):
    """The NameClash for a name that is a state and a country ("Georgia"), or None."""
    k = key(text)
    return next((v for name, v in NAME_CLASHES.items() if key(name) == k), None)


@functools.cache
def _and_names():
    """Normalised names that contain "and", which " and " / "&" must not split."""
    sources = [
        *(
            n
            for table in countries.SUBREGIONS.values()
            for s in table.SUBREGIONS
            for n in (s.name, *s.aliases)
        ),
        *(n for c in countries.COUNTRIES for n in (c.name, *c.aliases)),
        *(n for m in countries.METROS for n in (m.name, *m.aliases)),
        *(n for region in _regions.all_regions() for n in (region.name, *region.aliases)),
        *AND_NAMES,
    ]
    keys = (key(name.replace(",", " ")) for name in sources)
    return frozenset(k for k in keys if " and " in f" {k} ")
