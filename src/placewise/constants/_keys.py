"""How place names are compared: one normalised key per spelling, shared by the reference tables."""

import re
import unicodedata

_SEPARATORS = re.compile(r"[\s\-‐‑‒–—―−_]+")


def key(text):
    """Lower case, accents and dots dropped, '&' read as 'and', hyphens and runs of space as one space:
    "N.Y." -> "ny", "Québec" -> "quebec", "Trinidad & Tobago" -> "trinidad and tobago"."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("’", "'").replace(".", " ").replace("&", " and ")
    text = re.sub(r"(?<=\b\w) (?=\w\b)", "", _SEPARATORS.sub(" ", text).strip())  # "n y" -> "ny"
    return _SEPARATORS.sub(" ", text).strip()


_ABBREVIATIONS = (
    (re.compile(r"\bst\b"), "saint"),
    (re.compile(r"\bft\b"), "fort"),
    (re.compile(r"\bmt\b"), "mount"),
)


def city_key(text):
    """`key` with St / Ft / Mt spelled out, so "St Paul", "St. Paul" and "Saint Paul" compare equal."""
    k = key(text)
    for pattern, full in _ABBREVIATIONS:
        k = pattern.sub(full, k)
    return k
