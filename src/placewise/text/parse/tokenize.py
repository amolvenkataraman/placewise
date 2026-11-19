"""One place-string into its parts: hierarchy splits, codes peeled off, parentheses, noise dropped;
and the working copy of the location string they are read from, split while offsets into the raw
text survive."""

import functools
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
from .readings import _and_names, _readings

_NAME_WORDS = re.compile(r"[\w'.]+")
# location strings repeat the same pieces ("Toronto, ON", "Remote - US"): each piece is read once
_PIECE_CACHE = 1 << 14


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


_NOT_LETTERS = re.compile(r"[^A-Za-z]")
_SPACE_RUNS = re.compile(r"\s+")
_WORDS = re.compile(r"\S+")


@functools.lru_cache(maxsize=1 << 16)
def _is_upper(text):
    letters = _NOT_LETTERS.sub("", text)
    return bool(letters) and letters.isupper()


def _display(text):
    text = _SPACE_RUNS.sub(" ", text).strip(" -,:/")
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
    words = [(m.start(), m.end()) for m in _WORDS.finditer(chunk)]
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
    """The parts of text[start:end], one place-string, in reading order, and leftover asides. They
    depend on that text alone, so each distinct piece is read once; the tokens are fresh copies
    (grouping edits them), placed at `start`. The working text itself is left as it was."""
    tokens, leftovers = _piece(text.get(start, end))
    return [
        _Token(t, s + start, e + start, kind, readings, metro, alias, macro, upper)
        for t, s, e, kind, readings, metro, alias, macro, upper in tokens
    ], list(leftovers)


@functools.lru_cache(maxsize=_PIECE_CACHE)
def _piece(chunk):
    tokens, leftovers = _read_piece(_Text(chunk), 0, len(chunk))
    fields = tuple(
        (t.text, t.start, t.end, t.kind, t.readings, t.metro, t.alias, t.macro, t.upper) for t in tokens
    )
    return fields, tuple(leftovers)


def _read_piece(text, start, end):
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
        text.put(s, saved)
        if _own_name(saved, tokens):  # "Bengaluru (BLR)": the city's airport code, not Belarus
            continue
        inner = _plain_tokens(text, s, e)
        if not inner:
            continue
        if all(t.kind == "junk" for t in tokens):
            tokens = [*tokens, *inner]
        elif all(t.kind == "region" or (t.kind == "alias" and t.readings) for t in inner):
            for t in inner:  # "Springfield (LA)": a short alias beside a city is a code
                t.kind = "region"
            tokens.extend(inner)
        else:
            leftovers.append(_display(saved))
    return tokens, leftovers


def _own_name(chunk, tokens):
    """Is `chunk` another name of a city in `tokens` ("Bengaluru (BLR)", "Guangzhou, CAN")? Then
    that city token becomes the alias, so it carries the city's country, and True."""
    alias = _metros.any_alias(chunk)
    if alias is None:
        return False
    for tok in tokens:
        if tok.kind == "alias" and (tok.alias.city, tok.alias.country) == (alias.city, alias.country):
            return True
        if tok.kind == "city" and _metros.key(tok.text) == _metros.key(alias.city):
            tok.kind, tok.alias, tok.readings = "alias", alias, ()
            return True
    return False


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
    tokens = [  # "Bengaluru, BLR": a city's own code after it says nothing more
        t
        for i, t in enumerate(tokens)
        if not (i and tokens[i - 1].kind in ("city", "alias") and t.kind in ("region", "alias"))
        or not _own_name(t.text, [tokens[i - 1]])
    ]
    if len([t for t in tokens if t.kind != "junk"]) > 1:
        for tok in tokens:  # "NY, USA": a short alias is a city only alone ("NY" is New York City)
            if tok.kind == "alias" and tok.readings and len(key(tok.text)) <= 2:
                tok.kind = "region"
    return tokens


def _broadest_first(tokens):
    places = [t for t in tokens if t.kind != "junk"]
    return len(places) >= 2 and places[0].kind == "region" and places[-1].kind in ("city", "alias")


# --- the working copy and its splits ---


class _Text:
    """The working copy of the raw string; same length, so spans stay valid as text is blanked."""

    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text

    def get(self, start, end):
        return self.text[start:end]

    def blank(self, start, end):
        if end > start:
            self.text = f"{self.text[:start]}{' ' * (end - start)}{self.text[end:]}"

    def put(self, start, chunk):
        """Write `chunk` back over text[start:start + len(chunk)] (undoing a blank)."""
        self.text = f"{self.text[:start]}{chunk}{self.text[start + len(chunk) :]}"


def _trim(text, start, end):
    """(start, end) with surrounding whitespace removed."""
    chunk = text.get(start, end)
    stripped = chunk.strip()
    if not stripped:
        return start, start
    lead = len(chunk) - len(chunk.lstrip())
    return start + lead, start + lead + len(stripped)


def _split(text, start, end, pattern, keep=None):
    """Spans between matches of `pattern` in text[start:end], outside parentheses; `keep(match)`
    returning True skips a separator."""
    chunk = text.get(start, end)
    inside = _inside_parens(chunk) if "(" in chunk else None
    spans, last = [], 0
    for m in pattern.finditer(chunk):
        if m.end() == m.start() and m.start() in (0, len(chunk)):
            continue
        if (inside is not None and inside[m.start()]) or (keep and keep(chunk, m)):
            continue
        spans.append((start + last, start + m.start()))
        last = m.end()
    spans.append((start + last, end))
    return [s for s in spans if s[1] > s[0]]


def _inside_parens(chunk):
    """Per character: is it inside parentheses?"""
    depth, inside = 0, []
    for c in chunk:
        depth += c == "("
        inside.append(depth > 0)
        depth -= c == ")" and depth > 0
    return inside


def _protected_and(chunk, m):
    """Is this " and " / "&" inside a name such as "Trinidad and Tobago"?"""
    sep = m.group().strip().lower()
    if sep not in {"and", "&"}:
        return False
    left = _NAME_WORDS.findall(chunk[: m.start()])[-8:]
    right = _NAME_WORDS.findall(chunk[m.end() :])[:8]
    names = _and_names()
    for i in range(len(left)):
        for j in range(1, len(right) + 1):
            if key(" ".join([*left[i:], "and", *right[:j]])) in names:
                return True
    return False
