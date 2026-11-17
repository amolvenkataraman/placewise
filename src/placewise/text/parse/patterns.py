"""Regular expressions compiled from the vocabularies in constants.location_text and
constants.work_modes."""

import re

from placewise.constants import location_text as vocab
from placewise.constants import work_modes as modes
from placewise.constants.countries import can, usa


def _words(words):
    """Alternation of whole words; a space in a phrase also matches a hyphen or nothing."""
    return "|".join(re.escape(w).replace(r"\ ", r"[\s-]?") for w in words)


def _any(patterns):
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


DASHES = dict.fromkeys(map(ord, vocab.DASHES), "-")
SPACES = dict.fromkeys(map(ord, vocab.SPACES), " ")

NUMBER_WORDS = modes.NUMBER_WORDS
_NUM = modes.LOCATION_DAY_COUNT
_IN_OFFICE = modes.LOCATION_IN_OFFICE
_DAYS = (
    rf"{_NUM}(?:\s*(?:-|to|or)\s*{_NUM})?\s*(?:days?|x)\b(?:\s*(?:/|a|an|per|each|every)\s*(?:week|wk)\b)?"
)
DAY_NUMBER = re.compile(rf"\b{_NUM}\b", re.IGNORECASE)
# "in office 3 days/week", "2-3 days per week on-site": hybrid, or onsite at five days
OFFICE_DAYS = re.compile(
    rf"\b{_IN_OFFICE}\s*:?\s*(?:for\s+)?{_DAYS}|\b{_DAYS}\s*(?:of\s+)?(?:work\s+)?{_IN_OFFICE}", re.IGNORECASE
)
# "3 days/week" beside a mode: the office days of a hybrid role
WEEKLY_DAYS = re.compile(
    rf"\b{_NUM}(?:\s*(?:-|to|or)\s*{_NUM})?\s*(?:days?|x)\s*(?:/|a|per|each)\s*(?:week|wk)\b", re.IGNORECASE
)
OFFICE_WEEKDAYS = re.compile(rf"\b{_IN_OFFICE}\s+(?:on\s+)?{modes.LOCATION_WEEKDAY}\b", re.IGNORECASE)
NEGATED_REMOTE = _any(modes.LOCATION_NEGATED_REMOTE)
HYBRID = _any(modes.LOCATION_HYBRID)
REMOTE = _any(modes.LOCATION_REMOTE)
ONSITE = _any(modes.LOCATION_ONSITE)

_MORE_WORDS = _words(vocab.LIST_MORE_WORDS)
MORE = re.compile(
    rf"\s*\+\s*\d+\s*(?:{_MORE_WORDS}|locations?)?\b(?:\s+locations?\b)?"
    rf"|\band\s+\d+\s+(?:{_MORE_WORDS})\b(?:\s+locations?\b)?"
    rf"|\b(?:{_words(vocab.LIST_MARKER_WORDS)}|\d+)\s+(?:office\s+)?locations?\b",
    re.IGNORECASE,
)
LEVEL1 = re.compile("[" + re.escape("".join(vocab.PLACE_SEPARATORS)) + "]")
# separators keep the space after them in the next piece, so a blanked "Remote" stays inside it
LEVEL2 = re.compile(
    rf"\s+(?:{_words(vocab.ALTERNATIVE_WORDS)})(?=\s)|\s*&|\s+/(?=\s)|(?<=[A-Za-z]{{2}})/(?=[A-Za-z]{{2}})",
    re.IGNORECASE,
)
HIERARCHY = re.compile(r"\s*,\s*|\s+-\s*|\s*-\s+")
LEADING = re.compile(
    rf"^[\s\-:,/]*(?:(?:{_words(vocab.LEADING_WORDS)})\b(?:\s+the\b)?(?=[\s\-:,/]+\S)[\s\-:,/]*)*",
    re.IGNORECASE,
)
NOISE = re.compile(rf"\b(?:{_words(vocab.NOISE_WORDS + vocab.DIRECTIONS)})\b", re.IGNORECASE)
NOT_A_CITY = re.compile(
    rf"\d|\b(?:{_words(vocab.NOT_A_CITY_WORDS + vocab.PLACEHOLDERS)})(?!\w)", re.IGNORECASE
)
PARENS = re.compile(r"\(([^()]*)\)")
# postal codes: US ZIP / ZIP+4, Canadian postal codes and Indian PINs
POSTAL_CODES = (usa.country.POSTAL_CODE, can.country.POSTAL_CODE, re.compile(r"\b[1-9]\d{5}\b"))
