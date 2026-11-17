"""How place names are compared: one normalised key per spelling, shared by the reference tables."""

import functools
import re
import unicodedata

_SEPARATORS = re.compile(r"[\s\-‐‑‒–—―−_]+")
_SINGLE_LETTER_GAP = re.compile(r"(?<=\b\w) (?=\w\b)")  # "n y" -> "ny"
# keys are asked for the same few thousand names again and again; the cache stays bounded
_CACHE_SIZE = 1 << 16


@functools.lru_cache(maxsize=_CACHE_SIZE)
def key(text):
    """Lower case, accents and dots dropped, '&' read as 'and', hyphens and runs of space as one space:
    "N.Y." -> "ny", "Québec" -> "quebec", "Trinidad & Tobago" -> "trinidad and tobago"."""
    if not text.isascii():  # ASCII has nothing to decompose and no combining marks
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'").replace(".", " ").replace("&", " and ")
    text = _SINGLE_LETTER_GAP.sub("", _SEPARATORS.sub(" ", text).strip())
    return _SEPARATORS.sub(" ", text).strip()


_ABBREVIATIONS = (
    (re.compile(r"\bst\b"), "saint"),
    (re.compile(r"\bft\b"), "fort"),
    (re.compile(r"\bmt\b"), "mount"),
)


@functools.lru_cache(maxsize=_CACHE_SIZE)
def city_key(text):
    """`key` with St / Ft / Mt spelled out, so "St Paul", "St. Paul" and "Saint Paul" compare equal."""
    k = key(text)
    for pattern, full in _ABBREVIATIONS:
        k = pattern.sub(full, k)
    return k
