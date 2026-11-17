"""One place's candidates: readings that agree, evidence and context, the gazetteer, confidence."""

import re
from dataclasses import dataclass

from placewise.constants._keys import key
from placewise.model.places import Place

from .. import cities as _cities
from .. import metros as _metros
from .group import _consistent
from .model import LocationPart
from .readings import _admin1_name, _ambiguous_city, _name_clash, _Reading
from .tokenize import _display


@dataclass
class _Candidate:
    country: str | None
    admin1: str | None = None
    admin1_name: str | None = None
    weight: float = 1.0
    no_city: bool = False  # a reading of the city token itself as a region ("LA" as Louisiana)
    place: Place | None = None


def _weights(n):
    base = {1: (1.0,), 2: (0.8, 0.2), 3: (0.7, 0.2, 0.1)}
    if n in base:
        return base[n]
    raw = [0.5**i for i in range(n)]
    return tuple(w / sum(raw) for w in raw)


def _promote(cands, wanted, strength=0.9):
    """Move candidates passing `wanted` first, sharing `strength` among them."""
    hits = [c for c in cands if wanted(c)]
    if not hits or len(hits) == len(cands):
        return cands
    rest = [c for c in cands if not wanted(c)]
    for group, share in ((hits, strength), (rest, 1 - strength)):
        total = sum(c.weight for c in group) or 1
        for c in group:
            c.weight = share * c.weight / total
    return hits + rest


def _resolve(group, context, gazetteer):
    """The place a group names: its likeliest candidate, the others as alternatives."""
    allow_india = "IN" in context
    if group.metro is not None:
        metro = group.metro.metro
        city = None
        if group.city is not None:
            city = group.city.alias.city if group.city.kind == "alias" else group.city.text
        default_admin1 = (metro.admin1_of(city) if city else None) or metro.sole_admin1
        cands = []
        for combo in _consistent([t.readings for t in group.regions], allow_india) if group.regions else [()]:
            country = combo[0].country if combo else metro.country
            admin1 = next((r.admin1 for r in combo if r.admin1), None) or default_admin1
            if country == metro.country and (admin1 is None or admin1 in metro.admin1):
                cands.append(_Candidate(country, admin1))
        cands = cands[:1] or [_Candidate(metro.country, default_admin1)]
        return _finish(group, cands, city, metro, gazetteer, context)

    city_tok = group.city
    city = city_tok.text if city_tok else None
    alias = None
    if city_tok is not None and city_tok.kind == "alias":
        own = [_Reading(city_tok.alias.country, city_tok.alias.admin1)]
        if not group.regions or _consistent([own, *[t.readings for t in group.regions]], True):
            alias = city_tok.alias
            city = alias.city
            if not group.regions:
                cands = [_Candidate(alias.country, alias.admin1)]
                others = [
                    r
                    for r in city_tok.readings
                    if not r.india_code and (r.country, r.admin1) != (alias.country, alias.admin1)
                ]
                if others:  # "LA": Los Angeles first, Louisiana second
                    cands[0].weight = 0.6
                    cands += [
                        _Candidate(r.country, r.admin1, weight=0.4 / len(others), no_city=True)
                        for r in others
                    ]
                return _finish(group, cands, city, alias.metro, gazetteer, context)
        else:
            city = _display(city_tok.text)

    if not group.regions:
        if city is None:
            return None
        table = _ambiguous_city(city) if city_tok.kind == "city" else None
        if not table:
            return _finish(group, [], city, None, gazetteer, context)
        cands = [_Candidate(c.country, c.admin1, c.admin1_name, c.weight) for c in table]
        return _finish(group, _promote(cands, lambda c: c.country in context), city, None, gazetteer, context)

    region_readings = [t.readings for t in group.regions]
    combos = _consistent(region_readings, allow_india)
    if city:
        # an Indian code counts beside a known city in that state ("Mumbai, MH")
        extra = [
            c
            for c in _consistent(region_readings, True)
            if c not in combos
            and _cities.is_known(city, c[0].country, next((r.admin1 for r in c if r.admin1), None))
        ]
        combos = combos + extra
    if not combos:
        combos = [(r,) for r in group.regions[0].readings if not r.india_code] or [
            (r,) for r in group.regions[0].readings
        ]
    cands, seen = [], set()
    for combo in combos:
        country, admin1 = combo[0].country, next((r.admin1 for r in combo if r.admin1), None)
        if alias is not None and country == alias.country and admin1 is None:
            admin1 = alias.admin1  # "NYC, USA"
        if (country, admin1) not in seen:
            seen.add((country, admin1))
            cands.append(_Candidate(country, admin1))
    for c, w in zip(cands, _weights(len(cands)), strict=True):
        c.weight = w

    clash = _name_clash(group.regions[0].text) if len(group.regions) == 1 else None
    evidence = None
    if city:
        for c in cands:  # "Ottawa, Canada", "Toronto, CA": the admin1 of the one known city there
            if not c.admin1 and len(found := _cities.admin1s(city, c.country)) == 1:
                c.admin1 = next(iter(found))
        # the first reading a known city fits settles it: "Mumbai, MH", "Atlanta, Georgia", but
        # "Richmond, CA" stays California, the reading the text gives first
        evidence = next((c for c in cands if _cities.is_known(city, c.country, c.admin1)), None)
    if clash and len(cands) > 1:  # "Georgia"
        for c in cands:
            c.weight = 0.5 if not city else (0.7 if c.admin1 else 0.3)
        if city and any(key(city) == key(n) for n in clash.country_cities):
            evidence = next((c for c in cands if c.country == clash.country and not c.admin1), evidence)
    if (
        group.remote
        and not city
        and len(group.regions) == 1
        and len(key(group.regions[0].text)) == 2
        and len(cands) > 1
    ):  # "CA-Remote": a remote listing's lone code is its country
        cands = _promote(cands, lambda c: c.admin1 is None, 0.6)
    if evidence is not None:
        cands = _promote(cands, lambda c: c is evidence)
    elif context:
        cands = _promote(cands, lambda c: c.country in context)
    if not city:
        # a region name that a metro lists as a city, with only its country after it: "Delhi, India"
        first, top = group.regions[0], cands[0]
        if any(r.by_name for r in first.readings) and _metros.metro_of(first.text, top.country, top.admin1):
            city = _display(first.text)
    return _finish(group, cands, city, alias.metro if alias else None, gazetteer, context)


def _finish(group, cands, city, metro, gazetteer, context):
    """Gazetteer check, names and metro, then the LocationPart with its alternatives."""
    verified = False
    if gazetteer is not None and city:
        if cands:
            hits = []
            for c in cands:
                place = None if c.no_city else gazetteer.match(city, c.country, c.admin1)
                if place is not None:
                    c.place = place
                    hits.append(c)
            if hits:
                total = sum(c.weight for c in hits) or 1
                for c in hits:
                    c.weight /= total
                cands, verified = hits, True
        else:
            ctx = next(iter(context)) if len(context) == 1 else None
            place = gazetteer.match(city, ctx, None)
            if place is not None:
                codes = place.codes or {}
                country = codes.get("iso2") or codes.get("country") or ctx
                cands, verified = [_Candidate(country, codes.get("admin1"), place=place)], True
    if not cands:
        cands = [_Candidate(None, weight=0.5)]
    parts = []
    for c in cands:
        name = None if c.no_city else (c.place.name if c.place is not None else city)
        if metro is not None and c.country == metro.country and not c.no_city:
            region = metro.key
        else:
            found = _metros.metro_of(name, c.country, c.admin1) or _metros.metro_of(city, c.country, c.admin1)
            region = found.key if found and name else None
        parts.append(
            LocationPart(
                city=name,
                admin1_code=c.admin1,
                admin1_name=c.admin1_name or _admin1_name(c.country, c.admin1),
                country_iso2=c.country,
                region=region,
                confidence=round(min(max(c.weight, 0.0), 1.0), 6),
                span=group.span,
                city_verified=verified and c.place is not None,
                remote=group.remote,
                place=c.place,
            )
        )
    first, *rest = parts
    return LocationPart(**{**_fields(first), "alternatives": tuple(rest)})


def _fields(part):
    return {f: getattr(part, f) for f in part.__dataclass_fields__}


def _embedded(group, gazetteer):
    """A city the gazetteer knows inside site or address text: "1530 FM 973 Taylor, TX"."""
    if not group.junk or group.city or group.metro:
        return None
    combos = _consistent([t.readings for t in group.regions], True) if group.regions else [()]
    targets = [
        (c[0].country, next((r.admin1 for r in c if r.admin1), None)) if c else (None, None) for c in combos
    ]
    for tok in group.junk:
        words = [w for w in re.split(r"[\s\-/]+", tok.text) if w and not any(ch.isdigit() for ch in w)]
        for size in range(min(4, len(words)), 0, -1):
            for begin in range(len(words) - size, -1, -1):
                name = " ".join(words[begin : begin + size])
                for country, admin1 in targets:
                    if gazetteer.match(name, country, admin1) is not None:
                        return tok, name
    return None
