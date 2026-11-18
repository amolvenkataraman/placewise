"""Ranking candidates: score = match quality x prior x context, all vectorised.

    match term    match_score ** MATCH_POWER x the name kind's worth (x FUZZY_FACTOR for typos);
                  prefix matches PREFIX_FLOOR + (1 - PREFIX_FLOOR) x match_score instead
    prior term    PRIOR_FLOOR + (1 - PRIOR_FLOOR) x rank (the index's prominence, 0..1)
    context       "Name, Context": 1 inside the first reading, CONTEXT_LATER_READING inside a later
                  one, 0 outside (CONTEXT_MISS_FACTOR when nothing at all is inside)
    near          NEAR_FLOOR + (1 - NEAR_FLOOR) x exp(-km / NEAR_SCALE_KM), km from the near
                  point to the place's extent (its point less its radius)
    factor        per candidate: city aliases from location search, override rules

Constants: placewise.constants.search.
"""

import numpy as np

from placewise.constants import search as const
from placewise.constants.names import NAME_KINDS
from placewise.geo.distances import haversine

_NAME_KIND_FACTOR = np.array([const.NAME_KIND_FACTOR[k] for k in NAME_KINDS])


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
