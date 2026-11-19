"""parse_location and parse_address: the entry points."""

import functools

from placewise.constants import countries
from placewise.constants.location_text import ADDRESS_KEYS
from placewise.constants.work_modes import MODES

from .. import metros as _metros
from .group import _group
from .model import ParsedLocation
from .modes import _work_modes
from .patterns import ANY_POSTAL_CODE, DASHES, LEVEL1, LEVEL2, MORE, POSTAL_CODES, SPACES
from .resolve import _embedded, _resolve
from .tokenize import _protected_and, _split, _Text, _Token, _tokens


def _contexts(context):
    if context is None:
        return frozenset()
    if isinstance(context, str):
        context = [context]
    out = set()
    for c in context:
        code = countries.lookup(c)
        if code is None:
            raise ValueError(f"unknown context country {c!r}")
        out.add(code)
    return frozenset(out)


def parse_location(text, gazetteer=None, *, context=None):
    """Read a location string into a ParsedLocation.

    `gazetteer`: any object with `.match(city, country_iso2, admin1_code) -> Place | None`; when
    given, cities are checked against it. `context`: the country (or countries) the string most
    likely refers to, as a caller reading Canadian listings knows: it settles "London", "Georgia"
    and "Smallville, CA". When it's left out, places in the same string that are certain set it.
    """
    raw = text or ""
    ctx = _contexts(context)
    if gazetteer is None and type(raw) is str:  # the answer is immutable, so repeats share it
        return _parse_cached(raw, ctx)
    return _parse(raw, gazetteer, ctx)


# listings repeat the same few location strings; answers without a gazetteer are kept for them
_RESULT_CACHE = 1 << 14


@functools.lru_cache(maxsize=_RESULT_CACHE)
def _parse_cached(raw, ctx):
    return _parse(raw, None, ctx)


def _parse(raw, gazetteer, ctx):
    work = _Text(raw.translate(DASHES).translate(SPACES))
    multiple = False
    for m in MORE.finditer(work.get(0, len(raw))):
        multiple = True
        work.blank(m.start(), m.end())
    if not ANY_POSTAL_CODE.hopeless(work.text):
        for pattern in POSTAL_CODES:
            for m in pattern.finditer(work.get(0, len(raw))):
                work.blank(m.start(), m.end())

    modes, unparsed = set(), []
    segments = _split(work, 0, len(raw), LEVEL1)
    separators = set(LEVEL1.findall(work.get(0, len(raw))))
    seg_groups = []  # per segment: list of (group, piece_is_remote)
    for s, e in segments:
        found, remote_spans = _work_modes(work, s, e)
        modes |= found
        pieces = []
        for ps, pe in _split(work, s, e, LEVEL2, keep=_protected_and):
            is_remote = any(rs < pe and re_ > ps for rs, re_ in remote_spans)
            toks, leftovers = _tokens(work, ps, pe)
            unparsed.extend(leftovers)
            pieces.append((toks, is_remote))
        seg_groups.append(pieces)

    # "US | Massachusetts | Boston": one place written with bars
    if separators == {"|"} and len(seg_groups) > 1 and all(len(p) == 1 for p in seg_groups):
        toks = [t for p in seg_groups for t in p[0][0]]
        if all(len([t for t in p[0][0] if t.kind != "junk"]) == 1 for p in seg_groups):
            places = [t for t in toks if t.kind != "junk"]
            if places[0].kind == "region" and places[-1].kind in ("city", "alias"):
                toks.reverse()
            if len(_group(toks)) == 1:
                seg_groups = [[(toks, any(p[0][1] for p in seg_groups))]]

    # group tokens into places; remote country-only places pass their flag to their siblings
    groups, scope_macros = [], []
    for pieces in seg_groups:
        seg = []
        for toks, is_remote in pieces:
            piece_groups = _group(toks)
            for g in piece_groups:
                g.remote = is_remote
            seg.append((piece_groups, is_remote))
        country_only = [all(not g.city and not g.metro for g in pg) for pg, _ in seg]
        if any(r and co for (_, r), co in zip(seg, country_only, strict=True)):
            for (pg, _), co in zip(seg, country_only, strict=True):
                if co:
                    for g in pg:
                        g.remote = True
        for pg, _ in seg:
            groups.extend(pg)

    resolved = []
    for g in groups:
        if g.city is not None and g.city.kind == "macro":
            if g.remote:
                if g.city.macro.members is not None:
                    scope_macros.append(g.city.macro.name)
            else:
                unparsed.append(g.city.text)
            unparsed.extend(t.text for t in g.junk)
            continue
        hit = _embedded(g, gazetteer) if gazetteer is not None else None
        if hit is not None:
            tok, name = hit
            g.junk.remove(tok)
            g.city = _Token(name, tok.start, tok.end, "city")
        unparsed.extend(t.text for t in g.junk)
        resolved.append(g)

    def resolve_all(context):
        return [p for g in resolved if (p := _resolve(g, context, gazetteer)) is not None]

    parts = resolve_all(ctx)
    if not ctx:
        certain = {
            p.country_iso2 for p in parts if p.country_iso2 and not p.alternatives and p.confidence >= 0.9
        }
        if len(certain) == 1 and any(p.alternatives for p in parts):
            parts = [
                p if not p.alternatives else q
                for p, q in zip(parts, resolve_all(frozenset(certain)), strict=True)
            ]

    # one place given twice is one part
    unique, seen = [], {}
    for p in parts:
        k = (
            _metros.key(p.city) if p.city else None,
            p.admin1_code,
            p.country_iso2,
            p.region if not p.city else None,
        )
        if k in seen:
            continue
        seen[k] = p
        unique.append(p)

    scope = []
    for p in unique:
        if p.remote and p.country_iso2:
            scope.append(p.iso_3166_2 or p.country_iso2)
    scope.extend(scope_macros)
    work_modes = tuple(m for m in MODES if m in modes)
    return ParsedLocation(
        raw=raw,
        parts=tuple(unique),
        work_mode=work_modes[0] if work_modes else None,
        work_modes=work_modes,
        remote_scope=tuple(dict.fromkeys(scope)),
        multiple=multiple or len(unique) > 1,
        unparsed=tuple(u for u in dict.fromkeys(unparsed) if u),
    )


def parse_address(address, *, remote=False, gazetteer=None, context=None):
    """Read a structured address: JSON-LD PostalAddress (addressLocality, addressRegion,
    addressCountry, which may be {"name": ...}) or plain city / state / stateCode / country /
    countryCode keys. `remote=True` reads it as the place a remote listing is limited to."""
    values = []
    for keys in ADDRESS_KEYS:
        value = next((address[k] for k in keys if address.get(k)), None)
        if isinstance(value, dict):
            value = value.get("name")
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    text = ", ".join(values)
    if remote:
        text = f"Remote, {text}" if text else "Remote"
    return parse_location(text, gazetteer, context=context)
