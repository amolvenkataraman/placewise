"""Ranking candidates: score = match quality x prior x context, all vectorised.

    match term    match_score ** MATCH_POWER x the name kind's worth (x FUZZY_FACTOR for typos);
                  prefix matches PREFIX_FLOOR + (1 - PREFIX_FLOOR) x match_score instead
    prior term    PRIOR_FLOOR + (1 - PRIOR_FLOOR) x rank (the index's prominence, 0..1)
    context       "Name, Context": 1 inside the first reading, CONTEXT_LATER_READING inside a later
                  one, 0 outside (CONTEXT_MISS_FACTOR when nothing at all is inside)
    near          NEAR_FLOOR + (1 - NEAR_FLOOR) x exp(-km / NEAR_SCALE_KM), km from the near
                  point to the place's extent (its point less its radius)
    factor        per candidate: city aliases from location search, override rules
    named after   SHADOW_FACTOR for what is named after a place the query also names (a station
                  called Richmond), a code read as a word ("Goa"), 1 otherwise
    typing        TYPING_FACILITY_FACTOR for facilities matched by a prefix
    postal codes  other code matches score just below the best postal code match

Constants: placewise.constants.search.
"""

import numpy as np

from placewise.constants import search as const
from placewise.constants.names import ABBREVIATION, ALIAS, CODE, NAME_KINDS, PLACE_KINDS
from placewise.geo.distances import haversine

_NAME_KIND_FACTOR = np.array([const.NAME_KIND_FACTOR[k] for k in NAME_KINDS])
_PLACES = [PLACE_KINDS.index(k) for k in const.SHADOWING_KINDS]
_FACILITIES = [PLACE_KINDS.index(k) for k in const.FACILITY_KINDS]
_POSTAL = PLACE_KINDS.index("postal_code")
_AIRPORT = PLACE_KINDS.index("airport")


def base_scores(match, rank, name_kind, fuzzy, factor, prefix=None):
    """Match term x prior term x factor, before context. A prefix match's term is
    PREFIX_FLOOR + (1 - PREFIX_FLOOR) x match: while typing, how much of a name is typed says
    little about which place is meant, so the prior decides."""
    match = np.clip(np.asarray(match, dtype=np.float64), 0.0, 1.0)
    term = np.power(match, const.MATCH_POWER)
    if prefix is not None:
        soft = const.PREFIX_FLOOR + (1.0 - const.PREFIX_FLOOR) * match
        term = np.where(np.asarray(prefix, dtype=bool), soft, term)
    term = term * _NAME_KIND_FACTOR[np.asarray(name_kind)]
    term = np.where(np.asarray(fuzzy, dtype=bool), term * const.FUZZY_FACTOR, term)
    prior = const.PRIOR_FLOOR + (1.0 - const.PRIOR_FLOOR) * np.clip(np.asarray(rank, dtype=np.float64), 0, 1)
    return term * prior * np.asarray(factor, dtype=np.float64)


def context_factors(group, contexts, country, admin1):
    """Per candidate, how well it sits in its context. `group[i]` indexes `contexts` (a tuple of
    reading lists: (country alpha-2, admin1 code or None), likeliest first), -1 for none;
    `country` and `admin1` are where each candidate is (object arrays, None when unknown)."""
    group = np.asarray(group)
    out = np.ones(len(group))
    for g, wanted in enumerate(contexts):
        members = np.flatnonzero(group == g)
        if not len(members) or not wanted:
            continue
        got = np.zeros(len(members))
        for i, (cc, a1) in enumerate(wanted):
            hit = np.array([country[m] == cc and (a1 is None or admin1[m] == a1) for m in members])
            got = np.where(hit & (got == 0), 1.0 if i == 0 else const.CONTEXT_LATER_READING, got)
        out[members] = got if got.any() else const.CONTEXT_MISS_FACTOR
    return out


def near_factors(lat, lon, radius_km, near):
    """The boost for being near `near` ((lat, lon)), from each place's extent, not its point."""
    km = np.asarray(haversine(near[0], near[1], np.asarray(lat), np.asarray(lon)), dtype=np.float64)
    km = np.maximum(km - np.asarray(radius_km, dtype=np.float64), 0.0)
    return const.NEAR_FLOOR + (1.0 - const.NEAR_FLOOR) * np.exp(-km / const.NEAR_SCALE_KM)


def served_city_scores(population, km):
    """How well each city near an airport fits as the city it serves: population over distance
    (SERVED_CITY_D0_KM softens the first kilometres), so a big city a little farther away wins
    over the suburb the airport stands in."""
    population = np.asarray(population, dtype=np.float64)
    return population / (np.asarray(km, dtype=np.float64) + const.SERVED_CITY_D0_KM)


def best_first(scores, ties):
    """Candidate indexes by score, best first; `ties` (higher first) breaks equal scores."""
    return np.lexsort((-np.asarray(ties, dtype=np.float64), -np.asarray(scores, dtype=np.float64)))


def namesakes_after(scores, pool, key_of, typed_word):
    """`scores` with other code matches after a postal code (postal_codes_first), facilities after
    places while typing (typing_factors) and what is named after a place the query also names after
    it (named_after_factors: a station called Richmond, "Goa" as Genoa's airport code, San
    Francisco Zoo while typing "San Fran"). Only the best SHADOW_CANDIDATES of `pool` (gather.Pool)
    are compared by name; key_of(i) is candidate i's matched key."""
    if not len(pool):
        return scores
    scores = postal_codes_first(scores, pool.kind, pool.name_kind) * typing_factors(pool.kind, pool.prefix)
    live = np.flatnonzero(scores > 0)
    if len(live) < 2:
        return scores
    live = live[np.argsort(-scores[live], kind="stable")[: const.SHADOW_CANDIDATES]]
    keys = np.full(len(pool), None, dtype=object)
    for i in live.tolist():
        keys[i] = key_of(i)
    return scores * named_after_factors(pool.kind, pool.name_kind, pool.rank, keys, typed_word)


def named_after_factors(kind, name_kind, rank, keys, typed_word):
    """SHADOW_FACTOR for each candidate named after a place the query also matches, 1 for the rest.
    A place is a candidate of a SHADOWING_KINDS kind with a prior of SHADOW_MIN_RANK or more,
    matched by a name (not a code: Toronto found by "YYZ" leaves the airport alone). Named after
    it: FACILITY_KINDS of the same key, other kinds through an alias or abbreviation of that key
    (Boise National Forest as "Boise"), codes of that key when `typed_word` (the query has
    lowercase letters: "Goa") or, but for airport codes, when the place is abbreviated so ("SF" is
    San Francisco before a station's code; "DEL" stays Delhi's airport, not Delaware), and anything
    not a place
    whose key is the place's key and more words (while typing "San Fran": San Francisco Zoo).
    `keys` is each candidate's matched key, None for candidates not compared."""
    kind, name_kind = np.asarray(kind), np.asarray(name_kind)
    keys = np.asarray(keys, dtype=object)
    out = np.ones(len(kind))
    compared = np.array([k is not None for k in keys], dtype=bool)
    is_place = np.isin(kind, _PLACES)
    place = compared & is_place & (name_kind != CODE)
    place &= np.asarray(rank, dtype=np.float64) >= const.SHADOW_MIN_RANK
    if not place.any():
        return out
    named = set(keys[place])
    abbreviated = set(keys[place & (name_kind == ABBREVIATION)])
    code = name_kind == CODE
    facility = np.isin(kind, _FACILITIES)
    other = ~is_place & np.isin(name_kind, (ALIAS, ABBREVIATION))
    for i in np.flatnonzero(compared & ~place):
        k = keys[i]
        if code[i]:
            hit = (typed_word and k in named) or (k in abbreviated and kind[i] != _AIRPORT)
        elif k in named:
            hit = facility[i] or other[i]
        else:
            words = k.split()
            hit = not is_place[i] and any(" ".join(words[:j]) in named for j in range(1, len(words)))
        if hit:
            out[i] = const.SHADOW_FACTOR
    return out


def typing_factors(kind, prefix):
    """TYPING_FACILITY_FACTOR for facilities matched by a prefix (while typing "Toro", Toronto
    before Toron, a famous castle), 1 for the rest."""
    facility = np.isin(np.asarray(kind), _FACILITIES) & np.asarray(prefix, dtype=bool)
    return np.where(facility, const.TYPING_FACILITY_FACTOR, 1.0)


def postal_codes_first(scores, kind, name_kind):
    """`scores` with every code match other than a postal code scoring at most CODE_AFTER_POSTAL
    times the best postal code match ("10001" is a ZIP Code before a railway station's code)."""
    scores, kind, name_kind = np.asarray(scores, dtype=np.float64), np.asarray(kind), np.asarray(name_kind)
    code = name_kind == CODE
    postal = code & (kind == _POSTAL)
    if not postal.any():
        return scores
    cap = float(scores[postal].max()) * const.CODE_AFTER_POSTAL
    return np.where(code & ~postal, np.minimum(scores, cap), scores)
