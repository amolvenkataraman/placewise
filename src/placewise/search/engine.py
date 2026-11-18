"""The search engine: a query in, ranked Entities out (docs/search.md).

1. Read the query (query.parse_query): name and "Name, Context", codes, ids, coordinates.
2. Gather candidates from every pack's name index (gather): exact names, city aliases, curated
   region ids, override aliases, codes and ids; prefix matches while typing; then generic words
   dropped, a trailing context word, and typo-tolerant (fuzzy) matches when nothing prominent
   matched exactly.
3. Score them (rank): match x prior x the text's context x the caller's context (context).
4. Drop hidden places and generically named parks, put an airport code's served city first, merge
   one place found in several packs (dedupe), and build the Entities with their context, all at
   once (entities).
"""

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import search as const
from placewise.constants.countries.conventions import ALPHA3_ANY_CASE
from placewise.constants.names import CODE, PLACE_KINDS
from placewise.engine._within import generic_name
from placewise.geo.distances import haversine
from placewise.model import Add, BBox, Entity, Hide, Place, Point, RegionRule, Rename

from . import context as ctx_mod
from . import dedupe, entities, rank
from .gather import Gatherer
from .query import parse_query

_AIRPORT = PLACE_KINDS.index("airport")
_PARK = PLACE_KINDS.index("park")
_COUNTRY = PLACE_KINDS.index("country")
_WATER = PLACE_KINDS.index("water")
_SETTLEMENTS = frozenset(PLACE_KINDS.index(k) for k in const.SETTLEMENT_PREFERENCE)


class Search:
    """Forward search over a Geocoder's packs, with its overrides (alias, rename, hide rules)."""

    def __init__(self, geocoder, overrides=None):
        self.geocoder = geocoder
        self.overrides = overrides if overrides is not None else geocoder.overrides
        self.packs = geocoder.packs
        self.contexts = entities.Contexts(geocoder)
        rules = tuple(getattr(self.overrides, "rules", ()) or ())
        self.hidden = frozenset(
            r.id for r in rules if isinstance(r, Hide) or (isinstance(r, RegionRule) and r.remove)
        )
        self.renames = {r.id: r for r in rules if isinstance(r, Rename)}
        self.added = {r.id: r for r in rules if isinstance(r, Add) and r.id}

    @property
    def indexes(self):
        found = []
        for pos, pack in enumerate(self.packs):
            index = pack.names
            if index is not None:
                found.append((pos, pack, index))
        return found

    # -- public -------------------------------------------------------------------------------------

    def find(self, text, *, limit=10, prefix=False, worldview=None, geometry=False, **context):
        """Ranked Entities for `text`; see placewise.search.find for the arguments."""
        if limit < 1:
            return []
        q = parse_query(text)
        ctx = self.context(**context)
        if q.point is not None:
            return [self._point(q.point, worldview)]
        pool, scores, groups = self._search(q, ctx, limit, prefix)
        if not groups and not prefix:  # "Lake" within a region: the lakes there
            pool, scores, groups = self._search(q, ctx, limit, True)
        found = self._entities(pool, scores, groups, worldview, geometry)
        added = [_added(self.added[i]) for i in self._override_ids(q, ctx) if i in self.added]
        return (added + found)[:limit] if added else found

    def get(self, ident, *, worldview=None, geometry=False):
        """The Entity with placewise id `ident`; KeyError when no pack (or add rule) has it."""
        ident = str(ident).strip()
        scheme, _, rest = ident.partition(":")
        if scheme.lower() == const.GEO_SCHEME and rest:
            point = parse_query(rest.split(";")[0]).point
            if point is None:
                raise KeyError(f"{ident!r} is not a geo: URI (geo:lat,lon)")
            return self._point(point, worldview)
        ident = parse_query(ident).id or ident
        g = Gatherer(self.indexes)
        g.ids(ident)
        pool = g.pool()
        if not len(pool) or ident in self.hidden:
            if ident in self.added and ident not in self.hidden:
                return _added(self.added[ident])
            raise KeyError(f"no place with id {ident!r} in the open packs")
        scores = rank.base_scores(pool.match_score, pool.rank, pool.name_kind, pool.fuzzy, pool.factor)
        order = rank.best_first(scores, pool.rank)
        groups = self._merge(pool, order[: const.POOL_FACTOR])[:1]
        return self._entities(pool, scores, groups, worldview, geometry)[0]

    def context(self, *, country=None, admin1=None, state=None, near=None, radius_km=None, bbox=None,
                within=None, kinds=None, strict=True):  # fmt: skip
        """The caller's context arguments, checked and normalised (context.Context)."""
        countries = ctx_mod.countries_of(country)
        if admin1 is not None and state is not None and admin1 != state:
            raise ValueError("give admin1= or state=, not both")
        admin = ctx_mod.admin1_of(admin1 if admin1 is not None else state, countries)
        if radius_km is not None and (near is None or radius_km < 0):
            raise ValueError("radius_km needs near=(lat, lon) and can't be negative")
        return ctx_mod.Context(
            countries=countries,
            admin1=admin,
            near=_point(near) if near is not None else None,
            radius_km=float(radius_km) if radius_km is not None else None,
            bbox=_bbox(bbox) if bbox is not None else None,
            within=self._within(within) if within is not None else None,
            kinds=ctx_mod.kinds_of(kinds),
            strict=bool(strict),
        )

    # -- the steps ------------------------------------------------------------------------------------

    def _search(self, q, ctx, limit, prefix):
        """(pool, scores, groups): the merged groups of candidate indexes, best first."""
        if q.context_place and ctx.near is None:
            near = self._search(parse_query(q.context_place), self.context(), 1, False)
            if near[2]:
                i = near[2][0][0]
                ctx = _replace(ctx, near=(float(near[0].lat[i]), float(near[0].lon[i])))
        contexts = [ctx_mod.text_context(q.context, ctx.countries, ctx.admin1)]
        g = Gatherer(self.indexes)
        g.each("exact", q.key, group=0)
        if prefix:
            spatial = ctx.within is not None or ctx.bbox is not None or ctx.radius_km is not None
            many = const.PREFIX_FILTERED_LIMIT if spatial else const.CANDIDATES_PER_PACK
            g.each("prefix", q.key, many, prefix=True, group=0)
        for key in q.water_keys:
            g.each("exact", key, group=0, factor=const.WATER_WORD_FACTOR, kinds=(_WATER,))
        for key, reading in q.aliases:
            contexts.append(ctx_mod.text_context((reading,), ctx.countries, ctx.admin1))
            g.each("exact", key, group=len(contexts) - 1, factor=const.CITY_ALIAS_FACTOR)
        if q.code:
            g.each("codes", q.code)
        if q.id:
            g.ids(q.id)
        for ident in q.region_ids:
            g.ids(ident)
        for ident in self._override_ids(q, ctx):
            g.ids(ident, factor=const.OVERRIDE_BOOST)
        if g.best_prior() < const.FUZZY_BELOW_PRIOR:
            for key in q.fallback_keys:
                g.each("exact", key, group=0)
            if q.trailing is not None and q.trailing.context_place:
                if self._known(q.trailing.key):  # "Union Station Toronto": "Union Station, Toronto"
                    comma = parse_query(f"{q.trailing.name}, {q.trailing.context_place}")
                    return self._search(comma, ctx, limit, prefix)
            elif q.trailing is not None:
                contexts.append(ctx_mod.text_context(q.trailing.context, ctx.countries, ctx.admin1))
                g.each("exact", q.trailing.key, group=len(contexts) - 1)
        if g.best_prior() < const.FUZZY_BELOW_PRIOR:
            g.each("fuzzy", q.key, const.CANDIDATES_PER_PACK, fuzzy=True, group=0)
        pool = g.pool()
        scores = self._score(pool, contexts, ctx)
        word = any(c.islower() for c in q.raw)  # "Goa" is a name, "GOA" may be a code
        scores = rank.namesakes_after(
            scores, pool, lambda i: self.packs[pool.pack[i]].names.key(pool.entry[i]), word
        )
        pool, scores = self._served(q, ctx, pool, scores)
        order = rank.best_first(scores, pool.rank)
        order = order[scores[order] > 0][: const.POOL_FACTOR * limit + const.POOL_FACTOR]
        order = self._visible(pool, order)
        return pool, scores, self._merge(pool, order)[:limit]

    def _known(self, key):
        """Whether `key` is a prominent enough name, exactly, in some pack."""
        probe = Gatherer(self.indexes)
        probe.each("exact", key, group=0)
        return probe.best_prior() >= const.FUZZY_BELOW_PRIOR

    def _score(self, pool, contexts, ctx):
        scores = rank.base_scores(
            pool.match_score, pool.rank, pool.name_kind, pool.fuzzy, pool.factor, pool.prefix
        )
        if not len(pool):
            return scores
        needs = ctx.needs_where or any(contexts)
        where = ctx_mod.Where(self.geocoder.admin, pool.lat, pool.lon) if needs else None
        if any(contexts):
            scores = scores * rank.context_factors(pool.group, contexts, where.country, where.admin1)
        scores = scores * ctx_mod.factors(ctx, pool.lat, pool.lon, pool.radius_km, pool.kind, where)
        if ctx.near is not None:
            scores = scores * rank.near_factors(pool.lat, pool.lon, pool.radius_km, ctx.near)
        # one feature matched by several names counts once, by its best
        ident = pool.pack * (1 << 40) + pool.layer.astype(np.int64) * (1 << 32) + pool.row
        order = np.lexsort((-scores, ident))
        first = np.ones(len(order), dtype=bool)
        first[1:] = ident[order][1:] != ident[order][:-1]
        keep = np.zeros(len(pool), dtype=bool)
        keep[order[first]] = True
        return np.where(keep, scores, 0.0)

    def _served(self, q, ctx, pool, scores):
        """An airport code without kinds means the city it serves: that city goes right above it."""
        if not q.code or q.airport or (ctx.kinds is not None and _AIRPORT in ctx.kinds) or not len(pool):
            return pool, scores
        hits = np.flatnonzero((pool.kind == _AIRPORT) & (pool.name_kind == CODE) & (scores > 0))
        if not len(hits):
            return pool, scores
        best = hits[np.argmax(scores[hits])]
        city = self._served_city(pool, best)
        if city is None:
            return pool, scores
        ident, name, lat, lon = city
        world = (self.geocoder.layers.world(lookup_const.CITIES) or "").partition("/")[0]
        g = Gatherer([x for x in self.indexes if x[1].name == world])
        g.ids(ident)  # the city's own row, then its namesakes in every pack
        g.indexes = self.indexes
        g.each("exact", name)
        extra = g.pool()
        if not len(extra):
            return pool, scores
        km = np.asarray(haversine(lat, lon, extra.lat, extra.lon))
        near = (km <= np.maximum(extra.radius_km, const.DEDUPE_POINT_KM)) & np.isin(
            extra.kind, list(_SETTLEMENTS)
        )
        extra = extra.take(np.flatnonzero(near))
        if ctx.kinds is not None:
            extra = extra.take(np.flatnonzero(np.isin(extra.kind, list(ctx.kinds))))
        if not len(extra):
            return pool, scores
        top = scores[best] * const.SERVED_CITY_FACTOR
        added = top * (0.99 + 0.01 * extra.rank.astype(np.float64))
        scores = scores.copy()
        airport = float(added.min()) * const.AIRPORT_AFTER_CITY
        scores[best] = airport
        if len(q.code) == 3 and q.code.upper() not in ALPHA3_ANY_CASE:
            country = (pool.kind == _COUNTRY) & (pool.name_kind == CODE) & (scores > airport)
            scores[country] = airport * const.COUNTRY_CODE_BELOW_AIRPORT
        merged = type(pool)(
            **{f: np.concatenate([getattr(pool, f), getattr(extra, f)]) for f in pool.__slots__}
        )
        return merged, np.concatenate([scores, added])

    def _served_city(self, pool, i):
        """(id, name, lat, lon) of the city airport candidate i serves, or None."""
        pack = self.packs[int(pool.pack[i])]
        index = pack.names
        airports = pack[index.layers[int(pool.layer[i])]]
        row = int(pool.row[i])
        cities = self.geocoder.layers.layer(lookup_const.CITIES)
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

    def _visible(self, pool, order):
        """Without hidden places and parks named only by a kind of land ("Open Space", in packs
        built before the park build dropped them: placewise.engine._within.generic_name)."""
        parks = pool.kind[order] == _PARK
        if not self.hidden and not parks.any():
            return order
        keep = []
        for i, park in zip(order.tolist(), parks.tolist(), strict=True):
            if park and self._generic(pool, i):
                continue
            if self.hidden and self._id(pool, i) in self.hidden:
                continue
            keep.append(i)
        return np.array(keep, dtype=np.int64)

    def _generic(self, pool, i):
        pack = self.packs[int(pool.pack[i])]
        return generic_name(pack[pack.names.layers[int(pool.layer[i])]].value("name", int(pool.row[i])) or "")

    def _id(self, pool, i):
        pack = self.packs[int(pool.pack[i])]
        return pack[pack.names.layers[int(pool.layer[i])]].value("id", int(pool.row[i]))

    def _merge(self, pool, order):
        items = {}
        for i in order:
            pack = self.packs[int(pool.pack[i])]
            index = pack.names
            layer = int(pool.layer[i])
            lyr = pack[index.layers[layer]]
            keys = {index.key(int(pool.entry[i])), entities.name_key(lyr.value("name", int(pool.row[i])))}
            polygon = index.layer_kind(layer) == "polygon"
            items[int(i)] = (
                frozenset(keys),
                PLACE_KINDS[int(pool.kind[i])],
                float(pool.lat[i]),
                float(pool.lon[i]),
                polygon,
                polygon and pack.name != lookup_const.DEFAULT_PACK,
                lyr.value("id", int(pool.row[i])),
            )

        inside = self._inside_pairs(pool, items)
        return dedupe.merge([int(i) for i in order], items, lambda i, lat, lon: (i, lat, lon) in inside)

    def _inside_pairs(self, pool, items):
        """{(i, lat, lon)}: candidate i's outline holds that point of another candidate it could be
        merged with; every such test of one layer in one vectorised call."""
        asks = {}  # (pack, layer) -> ([row], [lat], [lon], [i])
        for i, (keys_i, kind_i, *_rest) in items.items():
            if not items[i][4]:
                continue
            lyr = self._layer(pool, i)
            s, w, n, e = lyr.bboxes()[int(pool.row[i])].tolist()
            for j, (keys_j, kind_j, lat, lon, *_more) in items.items():
                if j == i or dedupe.family(kind_i) != dedupe.family(kind_j) or not (keys_i & keys_j):
                    continue
                if s <= lat <= n and (w <= lon <= e if w <= e else (lon >= w or lon <= e)):
                    ask = asks.setdefault((int(pool.pack[i]), int(pool.layer[i])), ([], [], [], []))
                    for part, value in zip(ask, (int(pool.row[i]), lat, lon, i), strict=True):
                        part.append(value)
        found = set()
        for (pack, layer), (rows, lats, lons, owners) in asks.items():
            lyr = self.packs[pack][self.packs[pack].names.layers[layer]]
            hit = np.atleast_1d(lyr.contains(np.array(lats), np.array(lons), np.array(rows)))
            found.update((owners[k], lats[k], lons[k]) for k in np.flatnonzero(hit))
        return found

    def _layer(self, pool, i):
        pack = self.packs[int(pool.pack[i])]
        return pack[pack.names.layers[int(pool.layer[i])]]

    def _entities(self, pool, scores, groups, worldview, geometry):
        if not groups:
            return []
        reps = [g[0] for g in groups]
        kinds = [PLACE_KINDS[int(pool.kind[i])] for i in reps]
        want_city = [entities.level(k) >= const.CONTEXT_LEVEL_DEFAULT for k in kinds]
        lats = [float(pool.lat[i]) for i in reps]
        lons = [float(pool.lon[i]) for i in reps]
        found = self.contexts.get(lats, lons, want_city, worldview)
        out = []
        for group, kind, where in zip(groups, kinds, found, strict=True):
            i = group[0]
            pack = self.packs[int(pool.pack[i])]
            built, resolved = entities.place(
                pack.names, pack, int(pool.layer[i]), int(pool.row[i]), kind, where, self.renames, geometry
            )
            alternates = []
            for j in group[1:]:
                other = self.packs[int(pool.pack[j])]
                alternates.append(
                    entities.light_place(
                        other.names,
                        other,
                        int(pool.layer[j]),
                        int(pool.row[j]),
                        int(pool.kind[j]),
                        float(pool.lat[j]),
                        float(pool.lon[j]),
                    )
                )
            score = max(float(scores[j]) for j in group)
            out.append(entities.entity(built, resolved, where, score, alternates, geometry))
        out.sort(key=lambda e: -e.score)
        return out

    def _point(self, point, worldview):
        lat, lon = point
        result = self.geocoder.lookup(lat, lon, worldview=worldview, near=False)
        return entities.point_entity(result, lat, lon)

    def _override_ids(self, q, ctx):
        resolve = getattr(self.overrides, "resolve_name", None)
        if resolve is None:
            return []
        country = next(iter(ctx.countries)) if len(ctx.countries) == 1 else None
        return resolve(q.raw, country=country, near=ctx.near)

    def _within(self, within):
        """A test (lat, lon) -> inside, for a place id, a name ("GTA") or an Entity."""
        if isinstance(within, Entity):
            within = within.place.id
        text = str(within)
        q = parse_query(text)
        if q.id:
            g = Gatherer(self.indexes)
            g.ids(q.id)
            pool = g.pool()
            groups = [[0]] if len(pool) else []
        else:
            pool, _, groups = self._search(q, ctx_mod.Context(), 1, False)
        if not groups:
            raise ValueError(f"within={within!r}: no such place in the open packs")
        i = groups[0][0]
        pack = self.packs[int(pool.pack[i])]
        layer_no, row = int(pool.layer[i]), int(pool.row[i])
        lyr = pack[pack.names.layers[layer_no]]
        if pack.names.layer_kind(layer_no) == "polygon":
            return lambda lat, lon: np.asarray(
                lyr.contains(lat, lon, np.full(np.shape(lat), row)), dtype=bool
            )
        clat, clon, radius = float(pool.lat[i]), float(pool.lon[i]), float(pool.radius_km[i])
        return lambda lat, lon: np.asarray(haversine(clat, clon, lat, lon)) <= radius


def _point(near):
    if hasattr(near, "lat"):
        return float(near.lat), float(near.lon)
    lat, lon = near
    Point(lat, lon)  # validates
    return float(lat), float(lon)


def _bbox(box):
    if isinstance(box, BBox):
        return box.as_tuple()
    return BBox(*box).as_tuple()


def _replace(ctx, **changes):
    import dataclasses

    return dataclasses.replace(ctx, **changes)


def _added(rule):
    """An Entity for a place an override rule adds (it has no pack row)."""
    built = Place(id=rule.id, name=rule.name, kind=rule.kind, point=rule.point)
    km = rule.radius_m / 1000
    from placewise.geo.shapes import bbox_around

    return Entity(
        place=built,
        point=rule.point,
        bbox=BBox(*bbox_around(rule.point.lat, rule.point.lon, km)),
        radius_km=km,
        score=1.0,
    )
