"""Reading a search query: the name, the context after a comma ("Springfield, IL", "Paris,
France", "Union Station, Toronto"), codes, placewise ids, coordinates typed as text, and the other
names location search knows for it (city aliases such as Bangalore, metros such as GTA)."""

import re
from dataclasses import dataclass

from placewise.constants import search as const
from placewise.constants._keys import city_key
from placewise.geo import coords
from placewise.text import metros
from placewise.text.parse import readings

# text that could be a coordinate pair: digits, signs, separators, degree marks, hemisphere letters
_COORDINATE_CHARS = re.compile(r"[\d\s.,;:/°º′″'\"+\-−NSEWnsew]+")
_DIGIT_RUNS = re.compile(r"\d+")
_QID = re.compile(r"[Qq]\d+")
_ID = re.compile(r"[A-Za-z][\w.\-]*:\S+")


@dataclass(frozen=True, slots=True)
class Query:
    """A query read for search. `context` lists the (country alpha-2, admin1 code or None)
    readings of the text after the comma, likeliest first; `context_place` is that text when it
    names no country or region (a city: "Union Station, Toronto"). `aliases` are (key, (country,
    admin1)) of other names of the city (Bombay -> mumbai); `region_ids` the ids of curated
    regions the name means (GTA -> region:gta); `fallback_keys` the name without generic words
    ("Peel Region" -> peel); `trailing` the query read with its last word as context ("Paris TX")."""

    raw: str
    name: str
    key: str
    context: tuple[tuple[str, str | None], ...] = ()
    context_place: str | None = None
    point: tuple[float, float] | None = None
    id: str | None = None
    code_like: bool = False  # the whole text could be a code
    aliases: tuple[tuple[str, tuple[str, str | None]], ...] = ()
    region_ids: tuple[str, ...] = ()
    fallback_keys: tuple[str, ...] = ()
    trailing: "Query | None" = None
    code: str | None = None  # the text matched against codes ("YYZ" in "YYZ airport")
    airport: bool = False  # the text says "airport": an airport code means the airport

    @property
    def is_id(self):
        return self.id is not None and not _QID.fullmatch(self.raw.strip())


def parse_query(text):
    """The Query for `text`; ValueError when it is empty."""
    raw = " ".join(str(text).split())
    if not raw:
        raise ValueError("empty query: give a place name, code, id or coordinates")
    point = _coordinates(raw)
    if point is not None:
        return Query(raw=raw, name=raw, key=city_key(raw), point=point)
    ident = _identifier(raw)
    parts = [p.strip() for p in raw.split(",")]
    name = parts[0] or raw
    context, place = _context([p for p in parts[1:] if p])
    if ident is not None and _ID.fullmatch(raw):
        name, context, place = raw, (), None
    key = city_key(name)
    code, airport = _code(raw)
    return Query(
        raw=raw,
        name=name,
        key=key,
        context=context,
        context_place=place,
        id=ident,
        code_like=_code_like(raw),
        aliases=_aliases(name, key),
        region_ids=_region_ids(name),
        fallback_keys=_fallback_keys(key),
        trailing=_trailing(raw, name, context, place),
        code=code,
        airport=airport,
    )


def _coordinates(raw):
    looks = "://" in raw or raw.startswith("www.")
    if not looks:
        looks = bool(_COORDINATE_CHARS.fullmatch(raw)) and len(_DIGIT_RUNS.findall(raw)) >= 2
    if not looks:
        return None
    try:
        return coords.parse(raw)
    except ValueError:
        return None


def _identifier(raw):
    if _QID.fullmatch(raw):
        return f"wikidata:Q{raw[1:]}"
    if _ID.fullmatch(raw) and not raw.split(const.ID_SEPARATOR, 1)[1].startswith("//"):
        return raw
    return None


def _code(raw):
    """(text to match as a code or None, whether the query asks for the airport)."""
    words = raw.split()
    rest = [w for w in words if w.lower() not in const.AIRPORT_WORDS]
    airport = len(rest) < len(words)
    text = " ".join(rest)
    return (text if text and _code_like(text) else None), airport


def _code_like(raw):
    if any(c.isspace() for c in raw) or len(raw) > const.CODE_MAX_CHARS:
        return False
    return any(c.isdigit() for c in raw) or "-" in raw or raw.isupper() or len(raw) <= 4


def _context(parts):
    """(readings, place): the readings every part agrees on, most specific part first; or the
    text itself as a place when the parts name no country or region."""
    if not parts:
        return (), None
    each = [readings(p) for p in parts]
    if not all(each):
        return (), ", ".join(parts)
    found = each[0]
    for other in each[1:]:
        countries = {c for c, _ in other}
        narrowed = [r for r in found if r[0] in countries]
        found = narrowed or found
    return tuple(dict.fromkeys(found)), None


def _aliases(name, key):
    alias = metros.city_alias(name)
    if alias is None or city_key(alias.city) == key:
        return ()
    return ((city_key(alias.city), (alias.country, alias.admin1)),)


def _region_ids(name):
    metro = metros.find(name)
    return (metro.id,) if metro is not None and metro.id else ()


def _fallback_keys(key):
    found = []
    for suffix in const.GENERIC_SUFFIXES:
        if key.endswith(f" {suffix}"):
            found.append(key[: -len(suffix) - 1].strip())
    for prefix in const.GENERIC_PREFIXES:
        if key.startswith(f"{prefix} "):
            found.append(key[len(prefix) + 1 :].strip())
    return tuple(k for k in dict.fromkeys(found) if k and k != key)


def _trailing(raw, name, context, place):
    """The query with its last word read as a country or region ("Paris TX", "Lyon France"),
    when there is no comma and that word reads as one; else, after a name of two words or more,
    as a place ("Union Station Toronto": context_place, which the engine tries only when the
    rest is a known name)."""
    if context or place or "," in raw:
        return None
    head, _, last = name.rpartition(" ")
    if not head or not (len(last) > 3 or last.isupper()):
        return None
    found = tuple(readings(last))
    if found:
        return Query(raw=raw, name=head, key=city_key(head), context=found)
    if " " in head and last[:1].isupper():
        return Query(raw=raw, name=head, key=city_key(head), context_place=last)
    return None
