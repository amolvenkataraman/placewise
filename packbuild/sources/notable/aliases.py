"""Aliases of a notable place: Wikidata's English aliases, cleaned and capped, plus short names.

Dropped: the name itself and repeats (compared as name keys, a leading "the" ignored), the place's
own codes (IATA, ICAO ... have columns of their own), web addresses, and anything over
MAX_LENGTH characters. Kept first: short forms (acronyms such as "UW", "IITB", "UWaterloo") and
aliases sharing a word with the name ("Shibuya Crossing", "Toronto Union Station"); then the rest
("Golden Temple" for Harmandir Sahib), shorter first; last, spelling variants of the name
("Harmandar Sahib", "Harimandir": a typo-tolerant search finds them anyway), at most MAX_ALIASES
in all.
"""

import re

from placewise.constants._keys import city_key

MAX_ALIASES = 6
MAX_LENGTH = 50
VARIANT_EDITS = 2  # a word at most this many letters (and a quarter of its length) from a name word
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


def _edits(a, b):
    """Levenshtein distance between two short strings."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def _near(word, other):
    return _edits(word, other) <= max(1, min(VARIANT_EDITS, len(word) // 4))


def variant(name, alias):
    """Whether `alias` is a spelling variant of `name`: each of its words is a word of the name or
    a few letters from one ("Harmandar Sahib", "Harimandir" for Harmandir Sahib), and one is not
    spelled as in the name ("Harmandir" alone is a part of the name, not a variant)."""
    words, mine = _key(name).split(), _key(alias).split()
    if not mine or all(w in words for w in mine):
        return False
    return all(any(w == o or _near(w, o) for o in words) for w in mine)


def short_names(name, kind):
    """Short names the build adds: "Mumbai Central railway station" -> "Mumbai Central station"."""
    if kind == "station" and (m := _STATION_SUFFIX.match(name)):
        return [f"{m[1]} station"]
    return []


def clean(name, aliases, codes=(), kind=""):
    """The aliases to keep, best first (see the module docstring)."""
    seen = {_key(name)} | {_key(c) for c in codes if c}
    words = _words(name)
    first, rest, variants = [], [], []
    candidates = [" ".join(a.split()) for a in [*short_names(name, kind), *aliases]]
    # short forms first, so "UWaterloo" wins over "uwaterloo" (one key)
    for alias in sorted(candidates, key=lambda a: not _SHORT_FORM.match(a)):
        k = _key(alias)
        if not k or k in seen or len(alias) > MAX_LENGTH or _DOMAIN.match(alias) or "|" in alias:
            continue
        seen.add(k)
        if _SHORT_FORM.match(alias):
            first.append(alias)
        elif variant(name, alias):
            variants.append(alias)
        else:
            (first if words & _words(alias) else rest).append(alias)
    rest.sort(key=len)
    variants.sort(key=len)
    return (first + rest + variants)[:MAX_ALIASES]
