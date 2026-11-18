"""Packs on demand for a Geocoder that opened its packs from the store: before a batch lookup or a
search, work out the countries involved (from the world pack's country polygons) and the kinds of
place asked for, let the store fetch what auto mode allows (placewise.store.ondemand), and attach
the new packs. Manual and locked modes never download; the store hints once instead.

A batch is checked once, before any point is looked up, and only while the store still has a
pack worth fetching (Store.wants), so a lookup with everything installed costs nothing extra.
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.constants.names import PLACE_KINDS
from placewise.constants.store import COVERS_WORLD, SEARCH_KIND_PACKS

from ._index import best_per_query

OPTIONAL_PACKS = const.OPTIONAL_PACKS
_USABLE = frozenset(OPTIONAL_PACKS)
_CONTEXT = ("country", "admin1", "state", "near", "kinds")
_KM_PER_DEGREE = 111.0  # of latitude; longitude degrees are never longer, so the margin is generous


def before_lookup(geocoder, lats, lons, worldview):
    """Fetch and attach the packs a batch of points needs, if the store has any left to fetch."""
    store = geocoder._store
    pending = store.pending(usable=_USABLE) if store is not None else None
    if not pending:
        return
    try:
        only = None if COVERS_WORLD in pending else pending
        countries = point_countries(geocoder, lats, lons, worldview, only=only)
    except ValueError:
        return  # a bad worldview: the lookup itself reports it
    if countries:
        attach(geocoder, store.fetch_for(countries=countries, usable=_USABLE))


def before_search(geocoder, text, options):
    """Fetch and attach the packs a search needs: those of its country, admin1, near point or text
    context ("Paris, TX"), and of the kinds it asks for (kinds="park": the park packs there)."""
    store = geocoder._store
    if store is None:
        return
    try:
        ctx = geocoder.search.context(**{k: options[k] for k in _CONTEXT if k in options})
    except ValueError:
        return  # the search itself reports the bad argument
    from placewise.search.query import parse_query

    countries = set(ctx.countries) | {cc for cc, _ in ctx.admin1 if cc}
    countries |= {cc for cc, _ in parse_query(text).context if cc}
    if ctx.near is not None:
        try:
            countries |= point_countries(geocoder, [ctx.near[0]], [ctx.near[1]], options.get("worldview"))
        except ValueError:
            return
    kinds = {
        SEARCH_KIND_PACKS[PLACE_KINDS[i]] for i in ctx.kinds or () if PLACE_KINDS[i] in SEARCH_KIND_PACKS
    }
    if countries or kinds:
        attach(geocoder, store.fetch_for(countries=countries, extra_kinds=kinds, usable=_USABLE))


def point_countries(geocoder, lats, lons, worldview=None, only=None):
    """The alpha-2 codes of the countries the valid points are in or just off (12 nmi); with a
    worldview other than de facto, every claimant of the area too, since that view may answer one.
    `only` (alpha-2 codes) skips points outside those countries' bounding boxes first, which is
    most of the cost saved when the packs still missing cover a few countries. Invalid points are
    skipped here: the lookup itself reports them."""
    countries = geocoder.layers.layer(const.COUNTRIES)
    views = geocoder.admin.worldviews
    if countries is None or views is None:
        return set()
    lat = np.asarray(lats, dtype=np.float64).ravel()
    lon = np.asarray(lons, dtype=np.float64).ravel()
    if lat.shape != lon.shape:
        return set()
    ok = np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
    de_facto = tuple(geocoder._order(worldview)[0]) == (const.DE_FACTO,)
    if only is not None and de_facto:
        ok &= _in_boxes(countries, views, only, lat, lon)
    lat, lon = lat[ok], lon[ok]
    if not len(lat):
        return set()
    cidx = np.atleast_1d(countries.query(lat, lon)).astype(np.int64)
    miss = np.flatnonzero(cidx < 0)
    if len(miss):
        q, f, d = countries.near_boundary(lat[miss], lon[miss], const.TERRITORIAL_KM)
        best = best_per_query(q, d, len(miss))
        cidx[miss[best >= 0]] = f[best[best >= 0]]
    rows = np.unique(cidx[cidx >= 0]).tolist()
    found = {views.code[r] for r in rows}
    if not de_facto:
        found |= {views.code[c] for r in rows for c in views.claimant_rows[r]}
    return {code for code in found if len(code) == 2}


def _in_boxes(countries, views, codes, lat, lon):
    """Points within the bounding box (widened by the 12 nmi offshore reach) of a countries row
    whose code is in `codes`; a box crossing the antimeridian has west > east."""
    rows = [r for r, code in enumerate(views.code) if code in codes]
    inside = np.zeros(len(lat), dtype=bool)
    if not rows:
        return inside
    margin = const.TERRITORIAL_KM / _KM_PER_DEGREE
    for south, west, north, east in countries.bboxes()[rows].tolist():
        lat_ok = (lat >= south - margin) & (lat <= north + margin)
        west, east = west - margin, east + margin
        lon_ok = (lon >= west) & (lon <= east) if west <= east else (lon >= west) | (lon <= east)
        inside |= lat_ok & lon_ok
    return inside


def attach(geocoder, paths):
    """Open the newly installed packs and rebuild the Geocoder around them (once per pack)."""
    if not paths:
        return
    from placewise.packs import open_pack

    with geocoder._attach_lock:
        have = {(p.name, p.version) for p in geocoder.packs}
        new = [pack for pack in map(open_pack, paths) if (pack.name, pack.version) not in have]
        if not new:
            return
        world, rest = geocoder.packs[:1], [*geocoder.packs[1:], *new]
        order = {name: i for i, name in enumerate(OPTIONAL_PACKS)}
        rest.sort(key=lambda p: order.get(p.name, len(order)))
        geocoder._use([*world, *rest])
