"""Aliases of a notable place: Wikidata's English aliases, cleaned and capped, plus short names.

Dropped: the name itself and repeats (compared as name keys, a leading "the" ignored), the place's
own codes (IATA, ICAO ... have columns of their own), web addresses, and anything over
MAX_LENGTH characters. Kept first: short forms (acronyms such as "UW", "IITB", "UWaterloo") and
aliases sharing a word with the name ("Shibuya Crossing", "Toronto Union Station"); then the rest
("Harmandir Sahib"), shorter first, at most MAX_ALIASES in all.
"""

import re

from placewise.constants._keys import city_key

MAX_ALIASES = 6
MAX_LENGTH = 50
_DOMAIN = re.compile(r"^[\w-]+(\.[\w-]+)*\.[a-z]{2,}(/\S*)?$")
_SHORT_FORM = re.compile(r"^(?=(?:.*[A-Z]){2})[A-Za-z0-9&.-]{2,12}$")
_STOP = frozenset({"the", "of", "and", "a", "at", "de", "la", "le", "in"})
# a station called "X railway station" is also "X station"
_STATION_SUFFIX = re.compile(r"^(.+?) (?:railway|train|metro|subway|MRT|rail) station$", re.IGNORECASE)


def _key(text):
    k = city_key(text)
    return k[4:] if k.startswith("the ") else k


def _words(text):
    return {w for w in _key(text).split() if w not in _STOP}


def short_names(name, kind):
    """Short names the build adds: "Mumbai Central railway station" -> "Mumbai Central station"."""
    if kind == "station" and (m := _STATION_SUFFIX.match(name)):
        return [f"{m[1]} station"]
    return []


def clean(name, aliases, codes=(), kind=""):
    """The aliases to keep, best first (see the module docstring)."""
    seen = {_key(name)} | {_key(c) for c in codes if c}
    words = _words(name)
    first, rest = [], []
    candidates = [" ".join(a.split()) for a in [*short_names(name, kind), *aliases]]
    # short forms first, so "UWaterloo" wins over "uwaterloo" (one key)
    for alias in sorted(candidates, key=lambda a: not _SHORT_FORM.match(a)):
        k = _key(alias)
        if not k or k in seen or len(alias) > MAX_LENGTH or _DOMAIN.match(alias) or "|" in alias:
            continue
        seen.add(k)
        (first if _SHORT_FORM.match(alias) or words & _words(alias) else rest).append(alias)
    rest.sort(key=len)
    return (first + rest)[:MAX_ALIASES]
