"""Regular expressions compiled from the vocabularies in constants.location_text and
constants.work_modes.

Most location strings contain none of the words a pattern looks for, and a failed scan of a long
alternation costs far more than a substring test. So each pattern is wrapped with the strings one of
which every match must contain (worked out from the parsed pattern, see `_required`), and ASCII text
containing none of them is answered without running the regular expression.
"""

import re

try:  # the parser behind re.compile: re._parser on 3.11+, sre_parse before
    from re import _parser as _sre_parse
except ImportError:  # pragma: no cover - Python 3.10
    import sre_parse as _sre_parse

from placewise.constants import location_text as vocab
from placewise.constants import work_modes as modes
from placewise.constants.countries import can, usa


def _words(words):
    """Alternation of whole words; a space in a phrase also matches a hyphen or nothing."""
    return "|".join(re.escape(w).replace(r"\ ", r"[\s-]?") for w in words)


def _any(patterns):
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


_DIGITS = "0123456789"
_MAX_CLASS = 16  # a character class of more characters than this is no help


def _op(code):
    return getattr(code, "name", str(code))


def _class_chars(items):
    """The characters a [class] matches, or None when they're too many to test for."""
    chars = ""
    for op, arg in items:
        name = _op(op)
        if name == "LITERAL" and arg < 128:
            chars += chr(arg)
        elif name == "RANGE" and arg[1] < 128 and arg[1] - arg[0] < _MAX_CLASS:
            chars += "".join(map(chr, range(arg[0], arg[1] + 1)))
        elif name == "CATEGORY" and _op(arg) == "CATEGORY_DIGIT":
            chars += _DIGITS
        else:
            return None
    return tuple(dict.fromkeys(chars.lower())) if len(chars) <= _MAX_CLASS else None


def _better(a, b):
    """The more selective of two requirements (longest shortest option, then fewest options)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if (min(map(len, a)), -len(a)) >= (min(map(len, b)), -len(b)) else b


def _required(items):
    """Strings, one of which (in lower case) every ASCII match of this parsed sequence contains;
    None when no such set is known. Only what must be matched counts: literal runs, groups,
    branches whose every arm requires something, and repeats of at least once."""
    best, run = None, ""

    def flush():
        nonlocal best, run
        if run:
            best = _better(best, (run.lower(),))
        run = ""

    for op, arg in items:
        name = _op(op)
        if name == "LITERAL" and arg < 128:
            run += chr(arg)
            continue
        flush()
        found = None
        if name == "IN":
            found = _class_chars(arg)
        elif name == "SUBPATTERN":
            found = _required(arg[-1])
        elif name == "ATOMIC_GROUP":
            found = _required(arg)
        elif name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT") and arg[0] >= 1:
            found = _required(arg[2])
        elif name == "BRANCH":
            arms = [_required(arm) for arm in arg[1]]
            if all(arms):
                found = tuple(dict.fromkeys(w for arm in arms for w in arm))
        best = _better(best, found)
    flush()
    return best


class _Prefiltered:
    """A compiled pattern that skips the scan when ASCII text has none of the required strings."""

    __slots__ = ("flags", "pattern", "regex", "words")

    def __init__(self, regex, words):
        self.regex, self.words = regex, words
        self.pattern, self.flags = regex.pattern, regex.flags

    def hopeless(self, text):
        """Can't the pattern match `text`? (False: it may.)"""
        if self.words is None or not text.isascii():
            return False
        low = text.lower()
        for word in self.words:  # noqa: SIM110 - a plain loop beats all() on this hot path
            if word in low:
                return False
        return True

    def finditer(self, text):
        return iter(()) if self.hopeless(text) else self.regex.finditer(text)

    def findall(self, text):
        return [] if self.hopeless(text) else self.regex.findall(text)

    def search(self, text):
        return None if self.hopeless(text) else self.regex.search(text)

    def match(self, text):
        return None if self.hopeless(text) else self.regex.match(text)

    def sub(self, repl, text):
        return text if self.hopeless(text) else self.regex.sub(repl, text)


def _none_of(*patterns):
    """A prefilter that is hopeless only for text none of `patterns` can match."""
    if all(isinstance(p, _Prefiltered) for p in patterns):
        return _Prefiltered(patterns[0].regex, tuple(dict.fromkeys(w for p in patterns for w in p.words)))
    return _Prefiltered(patterns[0], None)


def _prefiltered(regex):
    """`regex`, behind a prefilter when one can be worked out."""
    try:
        words = _required(list(_sre_parse.parse(regex.pattern, regex.flags)))
    except Exception:  # an internal parser that changed shape: no prefilter, same answers
        words = None
    return _Prefiltered(regex, words) if words else regex


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
OFFICE_DAYS, WEEKLY_DAYS, OFFICE_WEEKDAYS, NEGATED_REMOTE, HYBRID, REMOTE, ONSITE = map(
    _prefiltered, (OFFICE_DAYS, WEEKLY_DAYS, OFFICE_WEEKDAYS, NEGATED_REMOTE, HYBRID, REMOTE, ONSITE)
)

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
POSTAL_CODES = tuple(
    map(_prefiltered, (usa.country.POSTAL_CODE, can.country.POSTAL_CODE, re.compile(r"\b[1-9]\d{5}\b")))
)
MORE, LEVEL2, HIERARCHY, LEADING, NOISE, NOT_A_CITY = map(
    _prefiltered, (MORE, LEVEL2, HIERARCHY, LEADING, NOISE, NOT_A_CITY)
)
# text that none of these can match names no work mode (WEEKLY_DAYS only counts beside them)
ANY_MODE = _none_of(OFFICE_DAYS, OFFICE_WEEKDAYS, NEGATED_REMOTE, HYBRID, REMOTE, ONSITE)
ANY_POSTAL_CODE = _none_of(*POSTAL_CODES)
