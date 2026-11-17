"""One place-string into its parts: hierarchy splits, codes peeled off, parentheses, noise dropped."""

import re
from dataclasses import dataclass

from placewise.constants._keys import key

from .. import metros as _metros
from .. import regions as _regions
from .patterns import HIERARCHY as _HIERARCHY
from .patterns import LEADING as _LEADING
from .patterns import NOISE as _NOISE
from .patterns import NOT_A_CITY as _NOT_A_CITY
from .patterns import PARENS as _PARENS
from .readings import _readings
from .spans import _split, _trim


@dataclass
class _Token:
    text: str
    start: int
    end: int
    kind: str  # "city", "region", "metro", "alias", "macro", "junk"
    readings: tuple = ()
    metro: object = None
    alias: tuple | None = None  # (city, admin1, metro)
    macro: object = None
    upper: bool = False


def _is_upper(text):
    letters = re.sub(r"[^A-Za-z]", "", text)
    return bool(letters) and letters.isupper()


def _display(text):
    text = re.sub(r"\s+", " ", text).strip(" -,:/")
    if len(text) > 3 and _is_upper(text):
        text = text.title()
    return text


def _token(text, start, end, first):
    """Classify text[start:end] (already trimmed)."""
    chunk = text.get(start, end)
    upper = _is_upper(chunk)
    alias = _metros.city_alias(chunk)
    reads = _readings(chunk, upper)
    if alias and (first or not reads):
        return _Token(chunk, start, end, "alias", readings=reads, alias=alias, upper=upper)
    if (metro := _metros.find(chunk)) is not None:
        return _Token(chunk, start, end, "metro", metro=metro)
    if not reads and not _metros.is_member_city(chunk):
        for m in _NOISE.finditer(chunk):
            text.blank(start + m.start(), start + m.end())
        start, end = _trim(text, start, end)
        chunk = text.get(start, end)
        m = _LEADING.match(chunk)
        if m and m.end():
            text.blank(start, start + m.end())
            start, end = _trim(text, start, end)
            chunk = text.get(start, end)
        if not chunk.strip(" -,:/"):
            return None
        if (alias := _metros.city_alias(chunk)) is not None:
            return _Token(chunk, start, end, "alias", alias=alias)
        if (metro := _metros.find(chunk)) is not None:
            return _Token(chunk, start, end, "metro", metro=metro)
        upper = _is_upper(chunk)
        reads = _readings(chunk, upper)
    if reads:
        return _Token(chunk, start, end, "region", readings=reads, upper=upper)
    if (macro := _regions.find(chunk)) is not None:
        return _Token(chunk, start, end, "macro", macro=macro)
    if _NOT_A_CITY.search(chunk):
        return _Token(_display(chunk), start, end, "junk")
    return _Token(_display(chunk), start, end, "city")


def _code_like(chunk):
    """A region or country written as a code in capitals ("CA", "USA") or as a name ("Texas")."""
    reads = _readings(chunk, _is_upper(chunk))
    if not reads:
        return False
    k = key(chunk)
    return len(k) > 3 or (_is_upper(chunk) and len(k) <= 3)


def _expand(text, start, end):
    """Split one hierarchy chunk further: "US-CA-Menlo Park", "US.AZ.Tempe", "Austin TX USA"."""
    start, end = _trim(text, start, end)
    chunk = text.get(start, end)
    if not chunk:
        return []
    whole = (
        _readings(chunk, _is_upper(chunk))
        or _metros.find(chunk)
        or _metros.city_alias(chunk)
        or _regions.find(chunk)
    )
    if whole:
        return [(start, end)]
    for sep in ("-", "."):
        if sep in chunk and (sep == "-" or " " not in chunk.split(sep)[0]):
            pieces = chunk.split(sep)
            if len(pieces) > 1 and all(pieces) and (_code_like(pieces[0]) or _code_like(pieces[-1])):
                if sep == "." and not all(len(p.strip()) >= 2 for p in pieces):
                    continue
                spans, pos = [], start
                for piece in pieces:
                    spans.extend(_expand(text, pos, pos + len(piece)))
                    pos += len(piece) + 1
                return spans
    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", chunk)]
    if len(words) < 2:
        return [(start, end)]
    # leading code: "WI Madison", "VA Arlington"
    first = chunk[words[0][0] : words[0][1]]
    if len(key(first)) <= 3 and _is_upper(first) and _readings(first, True):
        return [(start + words[0][0], start + words[0][1]), *_expand(text, start + words[1][0], end)]
    # trailing region or country: "Austin TX", "Ottawa Canada", "Durham North Carolina"
    for n in (3, 2, 1):
        if len(words) - n < 1:
            continue
        tail = chunk[words[-n][0] :]
        k = key(tail)
        reads = _readings(tail, _is_upper(tail))
        if not reads:
            continue
        if len(k) <= 3 and not (n == 1 and _is_upper(tail)):
            continue
        if len(k) > 3 and not any(r.by_name for r in reads):
            continue
        head_end = start + words[-n - 1][1]
        return [*_expand(text, start, head_end), (start + words[-n][0], end)]
    return [(start, end)]


def _tokens(text, start, end):
    """The parts of one place-string, in reading order, and leftover asides. A parenthesis is an
    aside ("Montreal (St. Laurent)"), the place itself ("HQ (San Francisco, CA)") or more parts of
    it ("Austin (TX)")."""
    asides = []
    for m in _PARENS.finditer(text.get(start, end)):
        s, e = start + m.start(1), start + m.end(1)
        asides.append((s, e, text.get(s, e)))
        text.blank(start + m.start(), start + m.end())
    tokens, leftovers = _plain_tokens(text, start, end), []
    for s, e, saved in asides:
        text.chars[s:e] = list(saved)
        inner = _plain_tokens(text, s, e)
        if not inner:
            continue
        if all(t.kind == "junk" for t in tokens):
            tokens = [*tokens, *inner]
        elif all(t.kind == "region" for t in inner):
            tokens.extend(inner)
        else:
            leftovers.append(_display(saved))
    return tokens, leftovers


def _plain_tokens(text, start, end):
    m = _LEADING.match(text.get(start, end))
    if m and m.end():
        text.blank(start, start + m.end())
    tokens, reversed_inside = [], False
    for s, e in _split(text, start, end, _HIERARCHY):
        chunk_tokens = []
        for cs, ce in _expand(text, s, e):
            cs, ce = _trim(text, cs, ce)
            if ce > cs and (tok := _token(text, cs, ce, first=not tokens and not chunk_tokens)) is not None:
                chunk_tokens.append(tok)
        if _broadest_first(chunk_tokens):  # "US-CA-Menlo Park", "VA Arlington"
            chunk_tokens.reverse()
            reversed_inside = True
        tokens.extend(chunk_tokens)
    if not reversed_inside and _broadest_first(tokens):  # "US, CA, Santa Clara", "Texas - Austin"
        tokens.reverse()
    if len([t for t in tokens if t.kind != "junk"]) > 1:
        for tok in tokens:  # "NY, USA": a short alias is a city only alone ("NY" is New York City)
            if tok.kind == "alias" and tok.readings and len(key(tok.text)) <= 2:
                tok.kind = "region"
    return tokens


def _broadest_first(tokens):
    places = [t for t in tokens if t.kind != "junk"]
    return len(places) >= 2 and places[0].kind == "region" and places[-1].kind in ("city", "alias")
