"""Context from outside the query text: country=, admin1= (state=), near= (+ radius_km=), bbox=,
within=, kinds=, combined with the context written in the text ("Paris, TX"). Arguments win when
the two disagree. Filters drop what fails them; with strict=False they only push it down.

`Where` answers, for many points at once, the country (alpha-2) and admin1 code and name each is
in, by reverse lookup's country and admin1 rules on the de facto view, and how each was found
(Result.matches). `near_border` says which points are close enough to another country's or
region's coarse outline that the answer may be wrong."""

from dataclasses import dataclass

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import search as const
from placewise.constants.names import PLACE_KINDS
from placewise.engine._matches import matches as field_matches
from placewise.geo.distances import haversine
from placewise.text.parse import readings


@dataclass(frozen=True, slots=True)
class Context:
    """The caller's context, normalised. `countries` alpha-2 codes; `admin1` (country or None,
    code) pairs; `kinds` PLACE_KINDS indexes; `within` a polygon test or None."""

    countries: frozenset[str] = frozenset()
    admin1: tuple[tuple[str | None, str], ...] = ()
    near: tuple[float, float] | None = None
    radius_km: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    within: object = None  # callable (lat, lon arrays) -> bool array
    kinds: frozenset[int] | None = None
    strict: bool = True

    @property
    def needs_where(self):
        return bool(self.countries or self.admin1)


def countries_of(country):
    """Alpha-2 codes for a country argument: a code, name or alias, or a list of them."""
    if country is None:
        return frozenset()
    from placewise.world import country as lookup

    items = [country] if isinstance(country, str | int) else list(country)
    out = set()
    for item in items:
        try:
            out.add(lookup(item).alpha2)
        except KeyError as err:
            raise ValueError(f"country={item!r}: {err.args[0] if err.args else 'unknown'}") from None
    return frozenset(out)


def admin1_of(admin1, countries=frozenset()):
    """(country or None, code) pairs for an admin1 argument: "TX", "Texas", "US-TX", "Ontario"."""
    if admin1 is None:
        return ()
    items = [admin1] if isinstance(admin1, str) else list(admin1)
    out = []
    for item in items:
        text = str(item).strip()
        cc, sep, code = text.partition("-")
        if sep and len(cc) == 2 and cc.isalpha() and code and " " not in text:
            out.append((cc.upper(), code.upper()))
            continue
        found = [(c, a) for c, a in readings(text) if a is not None]
        if countries:
            found = [r for r in found if r[0] in countries] or found
        if not found:
            raise ValueError(f"admin1={item!r}: not a state, province or region placewise knows")
        out.extend(found)
    return tuple(dict.fromkeys(out))


def kinds_of(kinds):
    """PLACE_KINDS indexes for a kinds argument ("city", "park", PlaceKind.WATER, a list ...)."""
    if kinds is None:
        return None
    items = [kinds] if isinstance(kinds, str) or not hasattr(kinds, "__iter__") else list(kinds)
    out = set()
    for item in items:
        value = str(getattr(item, "value", item)).strip().lower().replace(" ", "_")
        value = const.KIND_ALIASES.get(value, value)
        if value not in PLACE_KINDS:
            raise ValueError(f"kinds: unknown kind {item!r}; known: {', '.join(PLACE_KINDS)}")
        out.add(PLACE_KINDS.index(value))
    return frozenset(out)


def text_context(readings_, countries, admin1):
    """The text's context readings that agree with the arguments (arguments win: readings
    in another country, or naming another admin1, are dropped; none left means none)."""
    out = []
    for cc, a1 in readings_:
        if countries and cc not in countries:
            continue
        if admin1 and a1 is not None and (cc, a1) not in admin1 and (None, a1) not in admin1:
            continue
        out.append((cc, a1))
    return tuple(out)


def factors(ctx, lat, lon, radius_km, kind, where):
    """Per candidate: 1 when it passes every filter of `ctx`, else 0 (strict) or
    CONTEXT_MISS_FACTOR per failed filter (strict=False)."""
    n = len(lat)
    ok = []
    if ctx.kinds is not None:
        ok.append(np.isin(kind, list(ctx.kinds)))
    if ctx.countries:
        ok.append(np.array([c in ctx.countries for c in where.country], dtype=bool))
    if ctx.admin1:
        ok.append(
            np.array(
                [
                    any((cc is None or c == cc) and a == code for cc, code in ctx.admin1)
                    for c, a in where.pairs()
                ],
                dtype=bool,
            )
        )
    if ctx.bbox is not None:
        s, w, nn, e = ctx.bbox
        in_lon = (lon >= w) & (lon <= e) if w <= e else (lon >= w) | (lon <= e)
        ok.append((lat >= s) & (lat <= nn) & in_lon)
    if ctx.near is not None and ctx.radius_km is not None:
        km = np.asarray(haversine(ctx.near[0], ctx.near[1], lat, lon)) - np.asarray(radius_km)
        ok.append(km <= ctx.radius_km)
    if ctx.within is not None:
        ok.append(np.asarray(ctx.within(lat, lon), dtype=bool))
    out = np.ones(n)
    for mask in ok:
        out = out * np.where(mask, 1.0, 0.0 if ctx.strict else const.CONTEXT_MISS_FACTOR)
    return out


class Where:
    """Country and admin1 of points as reverse lookup has them on the de facto view (the engine's
    Admin): the containing polygons, or, just off a coast, the nearest within the territorial sea
    (Natural Earth's 1:10m coast misses many harbour and waterfront points). Empty without layers."""

    def __init__(self, admin, lat, lon):
        n = len(lat)
        self.admin, self.lat, self.lon, self._a = admin, lat, lon, None
        self.country = np.full(n, None, dtype=object)
        self.admin1 = np.full(n, None, dtype=object)
        self.admin1_name = np.full(n, None, dtype=object)
        if not n or admin.countries is None:
            return
        a = self._a = {}
        admin.answer(a, np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64), _DE_FACTO)
        self.country[:] = admin.iso2_of_view(a)
        aidx = a["aidx"]
        hit = aidx >= 0
        if hit.any():
            self.admin1[hit] = admin.admin1.column("code")[aidx[hit]]
            self.admin1_name[hit] = admin.admin1.column("name")[aidx[hit]]
        for arr in (self.country, self.admin1, self.admin1_name):
            arr[arr == ""] = None

    def pairs(self):
        return zip(self.country, self.admin1, strict=True)

    def matches(self, i):
        """{"country": Match, "region": Match} for point i, as Result.matches has its country and
        admin1 (within the polygon, or offshore / nearest with the km to it); {} for no country."""
        a = self._a
        if a is None or self.country[i] is None:
            return {}
        layers, fields, sources = self.admin.layers, {}, {}
        for field, role, row, mode in (
            ("country", lookup_const.COUNTRIES, a["cidx"][i], a["cmode"][i]),
            ("admin1", lookup_const.ADMIN1, a["aidx"][i], a["amode"][i]),
        ):
            if row >= 0 and (field == "country" or self.admin1[i] is not None):
                fields[field], sources[field] = layers.place(role, int(row)), layers.source(role, mode)
        found = field_matches(fields, sources, float(self.lat[i]), float(self.lon[i]))
        return {_FIELD.get(f, f): m for f, m in found.items()}


def near_border(admin, lat, lon, km=const.CONTEXT_BORDER_KM):
    """(country, admin1) bool arrays: whether the outlines of two or more countries (admin1 units)
    of the world pack come within km of each point, so a coarse border may put it on the wrong
    side. A coast with nothing across it isn't a border: only one outline is near."""
    lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
    out = []
    for layer in (admin.countries, admin.admin1):
        if layer is None or not len(lat):
            out.append(np.zeros(len(lat), dtype=bool))
            continue
        q, _, _ = layer.near_boundary(lat, lon, km)  # one row per (point, feature) pair
        out.append(np.bincount(q, minlength=len(lat)) >= 2)
    return out[0], out[1]


_DE_FACTO = (lookup_const.DE_FACTO,)
_FIELD = {"admin1": "region"}  # Result field -> Entity field
