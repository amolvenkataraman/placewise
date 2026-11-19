"""Gathering candidates from every open pack's name index into one Pool (struct of arrays).

Each lookup's Candidates join the pool tagged with the pack they came from, whether they were a
fuzzy match, the context group they must sit in (-1: none; see rank.context_factors) and a factor
(city aliases, override rules)."""

from dataclasses import dataclass

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import search as const
from placewise.constants._keys import city_key
from placewise.constants.names import CODE
from placewise.geo.distances import haversine

from . import rank

_FIELDS = ("entry", "layer", "row", "kind", "rank", "name_kind", "match_score", "lat", "lon", "radius_km")


@dataclass(frozen=True, slots=True, eq=False)
class Pool:
    pack: np.ndarray
    entry: np.ndarray
    layer: np.ndarray
    row: np.ndarray
    kind: np.ndarray
    rank: np.ndarray
    name_kind: np.ndarray
    match_score: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    radius_km: np.ndarray
    fuzzy: np.ndarray
    prefix: np.ndarray
    group: np.ndarray
    factor: np.ndarray

    def __len__(self):
        return len(self.pack)

    def take(self, index):
        return Pool(**{f: getattr(self, f)[index] for f in self.__slots__})


class Gatherer:
    """Collects Candidates from the indexes: a list of (pack position, Pack, NameIndex)."""

    def __init__(self, indexes):
        self.indexes = indexes
        self.parts = []

    def add(self, pack, found, *, fuzzy=False, prefix=False, group=-1, factor=1.0, kinds=None, min_match=0.0):
        """Add `found` (Candidates) from pack position `pack`; `kinds` (PLACE_KINDS indexes) keeps
        only candidates of those kinds, `min_match` those matching at least that well."""
        if kinds is not None and len(found):
            found = found.take(np.flatnonzero(np.isin(np.asarray(found.kind), list(kinds))))
        if min_match > 0 and len(found):
            found = found.take(np.flatnonzero(np.asarray(found.match_score) >= min_match))
        if not len(found):
            return
        n = len(found)
        part = {f: np.asarray(getattr(found, f)) for f in _FIELDS}
        part["pack"] = np.full(n, pack, dtype=np.int64)
        part["fuzzy"] = np.full(n, fuzzy, dtype=bool)
        part["prefix"] = np.full(n, prefix, dtype=bool)
        part["group"] = np.full(n, group, dtype=np.int64)
        part["factor"] = np.full(n, factor, dtype=np.float64)
        self.parts.append(part)

    def each(self, method, *args, **options):
        """Ask every index `method(*args)` and add the answers with `options`."""
        for pos, _, index in self.indexes:
            self.add(pos, getattr(index, method)(*args), **options)

    def ids(self, ident, factor=1.0):
        """Every feature whose placewise id is `ident` (ids are codes of their own row)."""
        for pos, pack, index in self.indexes:
            found = index.codes(ident)
            if len(found):
                keep = np.asarray(found.name_kind) == CODE
                rows = [i for i in np.flatnonzero(keep) if _row_id(pack, index, found, i) == ident]
                self.add(pos, found.take(np.asarray(rows, dtype=np.int64)), factor=factor)

    def twins(self, kinds, name_kinds, limit, factors):
        """Add the places found so far by another name (an abbreviation: "PEI") under their own
        name from every pack: for the best `limit` such candidates of
        `kinds` (PLACE_KINDS indexes) matched by one of `name_kinds`, the rows of the same kind
        named as the candidate is and lying within its reach (either one's radius, at least
        DEDUPE_POINT_KM), each worth the name kind's factor (`factors`, by name kind). So a place
        ranks by its best pack: the world pack ranks Prince Edward Island by the people of its
        cities, the Canada pack as a province."""
        pool = self.pool()
        hits = np.flatnonzero(
            np.isin(pool.kind, list(kinds)) & np.isin(pool.name_kind, list(name_kinds)) & ~pool.fuzzy
        )
        hits = hits[np.argsort(-pool.rank[hits], kind="stable")][:limit]
        packs = {pos: (pack, index) for pos, pack, index in self.indexes}
        for i in hits.tolist():
            pack, index = packs[int(pool.pack[i])]
            name = pack[index.layers[int(pool.layer[i])]].value("name", int(pool.row[i]))
            if not name:
                continue
            for pos, _, other in self.indexes:
                found = other.exact(city_key(name))
                if not len(found):
                    continue
                km = np.asarray(haversine(pool.lat[i], pool.lon[i], found.lat, found.lon))
                reach = np.maximum(np.maximum(found.radius_km, pool.radius_km[i]), const.DEDUPE_POINT_KM)
                keep = (np.asarray(found.kind) == pool.kind[i]) & (km <= reach)
                factor = factors[int(pool.name_kind[i])] * float(pool.factor[i])
                self.add(pos, found.take(np.flatnonzero(keep)), group=int(pool.group[i]), factor=factor)

    def tails(self, key, tails, kinds, factor, places, km):
        """Add the candidates of `kinds` named `key` and one of `tails` ("O'Hare" + "international
        airport"), worth `factor`, but those within `km` of a candidate so far of `places` (kinds)
        matched exactly by a name: Begumpet Airport, at the Hyderabad neighbourhood, is named
        after it, and "Begumpet" means the neighbourhood."""
        spots = [
            (p["lat"][hit], p["lon"][hit])
            for p in self.parts
            if (
                hit := np.isin(p["kind"], list(places))
                & (p["name_kind"] != CODE)
                & ~p["fuzzy"]
                & ~p["prefix"]
            ).any()
        ]
        lat = np.concatenate([a for a, _ in spots]) if spots else np.zeros(0)
        lon = np.concatenate([b for _, b in spots]) if spots else np.zeros(0)
        for pos, _, index in self.indexes:
            for tail in tails:
                found = index.exact(f"{key} {tail}")
                if not len(found):
                    continue
                keep = np.isin(np.asarray(found.kind), list(kinds))
                for i in np.flatnonzero(keep):
                    if len(lat) and np.min(haversine(found.lat[i], found.lon[i], lat, lon)) <= km:
                        keep[i] = False
                self.add(pos, found.take(np.flatnonzero(keep)), group=0, factor=factor)

    def has_exact(self):
        """Whether anything so far matched exactly (not by a typo or a prefix)."""
        return any((~p["fuzzy"] & ~p["prefix"]).any() for p in self.parts)

    def has_place(self, kinds, min_rank):
        """Whether a candidate so far of `kinds` with a prior of `min_rank` or more was matched
        by a name (not a code), exactly."""
        for p in self.parts:
            named = np.isin(p["kind"], list(kinds)) & (p["rank"] >= min_rank) & (p["name_kind"] != CODE)
            if (named & ~p["fuzzy"] & ~p["prefix"]).any():
                return True
        return False

    def best_prior(self):
        return max((float(p["rank"].max()) for p in self.parts), default=-1.0)

    def pool(self):
        if not self.parts:
            ints = {"pack", "entry", "layer", "row", "kind", "name_kind", "group"}
            return Pool(
                **{
                    f: np.zeros(
                        0, dtype=np.int64 if f in ints else bool if f in ("fuzzy", "prefix") else np.float64
                    )
                    for f in Pool.__slots__
                }
            )
        return Pool(**{f: np.concatenate([p[f] for p in self.parts]) for f in Pool.__slots__})


def _row_id(pack, index, found, i):
    return pack[index.layers[int(found.layer[i])]].value("id", int(found.row[i]))


def served_city(packs, cities, pool, i):
    """(id, name, lat, lon) of the city (in the `cities` layer, which may be None) that airport
    candidate i of the pool serves, or None."""
    pack = packs[int(pool.pack[i])]
    index = pack.names
    airports = pack[index.layers[int(pool.layer[i])]]
    row = int(pool.row[i])
    if cities is None:
        return None
    served = airports.value(const.SERVED_COLUMN, row) if const.SERVED_COLUMN in airports.fields else None
    if served:
        rows = cities.find("id", served)
        if len(rows):
            c = int(rows[0])
            return served, cities.value("name", c), float(cities.lat[c]), float(cities.lon[c])
    country = airports.value("country", row) if "country" in airports.fields else None
    found, _ = cities.within(float(pool.lat[i]), float(pool.lon[i]), const.SERVED_CITY_KM)
    found = np.asarray(found, dtype=np.int64)
    if not len(found):
        return None
    if country:
        found = found[cities.column("country")[found] == country]
    codes = cities.column("feature_code")[found] if "feature_code" in cities.fields else None
    if codes is not None:
        found = found[~np.isin(codes, list(lookup_const.CITY_EXCLUDED_FEATURE_CODES))]
    if not len(found):
        return None
    km = haversine(float(pool.lat[i]), float(pool.lon[i]), cities.lat[found], cities.lon[found])
    fit = rank.served_city_scores(np.asarray(cities.column("population"))[found], km)
    c = int(found[np.argmax(fit)])
    return cities.value("id", c), cities.value("name", c), float(cities.lat[c]), float(cities.lon[c])
