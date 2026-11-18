"""The Geocoder: a point in, the places a person would name out (placewise.model.Result).

The rules, in the order they run (constants in placewise.constants.lookup):

1. country and admin1 (_admin), with the worldview order applied;
2. country packs' boundaries: admin1 corrected by their states, provinces or PIN areas (naming);
3. time zones from the zones the packs give their admin units (_timezones); GeoNames cities: the provisional
   city score, the nearest-city time zone where no polygon answered, notable cities (_cities);
4. country packs' names: sublocality, locality, city, borough, admin2, postal, regions (naming);
5. airport, and the nearest country far offshore (_nearby);
6. parks the point is within or near, from the park packs (_within);
7. the sea or lake a point is on, and the water beside it, when a water pack is open (_water);
8. notable places near it, when the world-notable pack is open (_notable);
9. the Results and their labels (_results).

`lookup_many` runs every spatial query for all points at once and then builds the Results;
`lookup` is `lookup_many` with one point, so the two always agree. A point given more than once
in a batch is looked up once, and its Result (frozen) is shared by every position that has it.
"""

import inspect
import threading

import numpy as np

from placewise.config import effective_worldview
from placewise.constants import lookup as const
from placewise.model import CityRule, PlaceKind, Settings
from placewise.packs import Pack, once, open_pack

from . import _nearby, _ondemand, _results
from ._admin import Admin
from ._cities import Cities
from ._layers import Layers
from ._notable import Notable
from ._timezones import Timezones
from ._water import Water
from ._within import Parks
from .naming import Naming


class Geocoder:
    """Reverse geocoder over one or more packs. For each world layer it needs (countries, admin1,
    cities, airports) it reads the first pack that has it; a missing layer leaves its fields empty.
    Country packs (us, ca, in) name the points in their country (placewise.engine.naming).

    packs: opened Pack objects or pack directories; default: the "world" pack from the store
    (downloaded on first use unless the data mode is locked) and the country packs installed
    beside it; in auto mode (settings.data.mode) the packs a batch or a search needs are fetched
    and attached before it runs (placewise.engine._ondemand). overrides: any object with
    `apply(result, lat, lon) -> Result`, applied last to every answer."""

    def __init__(self, packs=None, settings=None, store=None, overrides=None):
        self.settings = settings or Settings()
        self._store = None  # the store packs come from on demand; None for packs given explicitly
        self._attach_lock = threading.Lock()
        if packs is None:
            if store is None:
                from placewise.store import Store

                store = Store(settings=self.settings.data)
            packs = [store.ensure(const.DEFAULT_PACK), *_installed_country_packs(store)]
            if callable(getattr(store, "fetch_for", None)):
                self._store = store
        packs = [p if isinstance(p, Pack) else open_pack(p) for p in packs]
        if not packs:
            raise ValueError("a Geocoder needs at least one pack")
        self.overrides = overrides
        # placewise.overrides' engine takes relabel=; a plain `apply(result, lat, lon)` hook works too
        self._overrides_relabel = overrides is not None and _accepts(overrides.apply, "relabel")
        self._use(packs)

    def _use(self, packs):
        """Read `packs`: the layers, admin and every index built on first use start afresh (what
        attaching a pack fetched on demand needs)."""
        self.packs = packs
        self.layers = Layers(packs)
        self.admin = Admin(self.layers)
        self.data_version = "+".join(f"{p.name}-{p.version}" for p in packs)
        for name, attr in vars(type(self)).items():
            if isinstance(attr, once):
                self.__dict__.pop(name, None)

    def __repr__(self):
        return f"<Geocoder {self.data_version}>"

    @once
    def cities(self):
        return Cities(self.layers, self.admin) if self.layers.has(const.CITIES) else None

    @once
    def timezones(self):
        """The packs' time zones (placewise.engine._timezones), or None when no pack has any."""
        found = Timezones(self.layers, self.admin, self.naming)
        return found if found else None

    @once
    def parks(self):
        """The park packs' layers (placewise.engine._within), or None when no pack has any."""
        return Parks(self.packs, self.layers, self.settings.near) or None

    @once
    def water(self):
        """The water layers (placewise.engine._water); falsy when no pack has them."""
        return Water(self.packs, self.layers)

    @once
    def notable(self):
        """The world-notable pack's layer (placewise.engine._notable), or None when no pack has it."""
        return Notable(self.packs, self.layers) or None

    @once
    def naming(self):
        """The country packs' rules; they need the GeoNames cities beside them."""
        return Naming(self.packs, self.layers, self.admin, self.cities) if self.cities is not None else None

    @once
    def search(self):
        """Forward search over these packs (placewise.search.Search)."""
        from placewise.search import Search

        return Search(self)

    # -- public API -------------------------------------------------------------------------------

    def find(self, text, **options):
        """Places named `text`, best first (placewise.search.find has the options)."""
        _ondemand.before_search(self, text, options)
        return self.search.find(text, **options)

    def get(self, ident, **options):
        """The Entity with placewise id `ident` (placewise.search.get)."""
        return self.search.get(ident, **options)

    def lookup(self, lat, lon, *, worldview=None, near=True):
        """The Result for one point (WGS84 degrees)."""
        return self.lookup_many([lat], [lon], worldview=worldview, near=near)[0]

    def lookup_many(self, lats, lons, *, worldview=None, near=True):
        """Results for many points, one per point, in order. Vectorised: much faster per point.
        Exactly repeated points are looked up once and share one Result."""
        _ondemand.before_lookup(self, lats, lons, worldview)
        return self._lookup(lats, lons, worldview, near, everything=True)

    def _lookup_places(self, lats, lons, *, worldview=None):
        """Results whose country, admin1 ... postal and regions are as lookup_many(near=False) has
        them, without airport or water, the time zone only as the nearest city has it, and parks
        (`within`) only when an override rule could read them to set the city. Forward search's
        context: it skips the water step, whose shore index takes seconds to build on first use."""
        return self._lookup(lats, lons, worldview, False, everything=False)

    def _lookup(self, lats, lons, worldview, near, everything):
        lat = np.asarray(lats, dtype=np.float64).ravel()
        lon = np.asarray(lons, dtype=np.float64).ravel()
        if lat.shape != lon.shape:
            raise ValueError(f"{len(lat)} latitudes but {len(lon)} longitudes")
        bad = ~(np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180))
        if bad.any():
            i = int(np.flatnonzero(bad)[0])
            raise ValueError(f"point {i} ({lat[i]}, {lon[i]}) is not a valid WGS84 latitude/longitude")
        order, locked = self._order(worldview)
        if not len(lat):
            return []
        first, inverse = _repeats(lat, lon)
        if first is not None:  # each distinct point once, in order of first appearance
            unique = self._lookup(lat[first], lon[first], worldview, near, everything)
            return [unique[i] for i in inverse.tolist()]
        a, named = self._answer(lat, lon, order, near, everything)
        results = _results.build(self, lat, lon, a, named, order, locked)
        if self.overrides is not None:
            apply = self.overrides.apply
            extra = {"relabel": self._relabel} if self._overrides_relabel else {}
            results = [
                apply(r, x, y, **extra) for r, x, y in zip(results, lat.tolist(), lon.tolist(), strict=True)
            ]
        return results

    # -- the steps ----------------------------------------------------------------------------------

    def _answer(self, lat, lon, order, near, everything=True):
        """(a, named): the steps' arrays; without `everything`, only the places a point is in."""
        a = {}
        self.admin.answer(a, lat, lon, order)
        named = {}
        naming = self.naming
        work = naming.boundaries(a, lat, lon) if naming else ()
        if everything and self.timezones is not None:
            self.timezones.answer(a, lat, lon, work)
        if self.cities is not None:
            k_notable = max(const.NOTABLE_CANDIDATES, self.settings.near.max_near + 1)
            self.cities.answer(a, lat, lon, near, self._near_km(PlaceKind.LOCALITY), k_notable)
        if work:
            named = naming.names(a, lat, lon, work)
        if everything and self.layers.has(const.AIRPORTS):
            _nearby.airports(a, self.layers.layer(const.AIRPORTS), lat, lon, self._near_km(PlaceKind.AIRPORT))
        _nearby.water(a, self.layers.layer(const.COUNTRIES), lat, lon)
        if (everything or self._rules_read_parks) and self.parks is not None:
            a["parks"] = self.parks.answer(lat, lon, near)
        if everything and self.water:
            self.water.answer(a, lat, lon, self.layers.layer(const.COUNTRIES))
        if near and self.notable is not None:
            a["notable_places"] = self.notable.answer(lat, lon)
        return a, named

    # -- worldview, settings, overrides -------------------------------------------------------------

    @once
    def _rules_read_parks(self):
        """Whether the overrides could set a city from the parks a point is in: a city rule (its
        area may name a park), or a hook whose rules can't be seen."""
        if self.overrides is None:
            return False
        rules = getattr(self.overrides, "rules", None)
        return rules is None or any(isinstance(r, CityRule) for r in rules)

    def _order(self, worldview):
        """(order, locked): the request's spelling normalised ("xa", "XAA" -> "XA"), then the
        operator lock applied by placewise.config.effective_worldview, as the server does."""
        wv = self.admin.worldviews
        norm = wv.normalise if wv is not None else _plain_order
        requested = norm(worldview) if worldview is not None else None
        order, locked = effective_worldview(self.settings, requested)
        return norm(order), locked

    def _near_km(self, kind):
        """How far `near` / `airport` search for a kind: the settings, unless an override Tune rule
        for the whole kind sets near_km (per-place near_km can only narrow; the engine applies it)."""
        default = (
            self.settings.near.airport if kind == PlaceKind.AIRPORT else self.settings.near.notable_rural
        )
        tuning = getattr(self.overrides, "tuning", None)
        if tuning is None:
            return default
        return tuning(kind=kind).get("near_km", default)

    def _relabel(self, result):
        """The label recomposed from a Result's fields, for the override engine after a rename."""
        if result.country is None and result.admin1 is None:
            return result.label  # offshore labels name a reference place, not the result's fields
        return _results.compose(self.settings.label, result)


def _repeats(lat, lon):
    """(first, inverse) when some points repeat exactly (bit for bit: -0.0 is not 0.0): the
    position of each distinct point's first appearance, in order, and the distinct point of every
    point; (None, None) when none repeats."""
    if len(lat) < 2:
        return None, None
    bits = np.stack([lat, lon], axis=1).view(np.int64)
    _, first, inverse = np.unique(bits, axis=0, return_index=True, return_inverse=True)
    if len(first) == len(lat):
        return None, None
    order = np.argsort(first)
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    return first[order], rank[inverse.ravel()]


def _installed_country_packs(store):
    """The country packs, the world-water pack, the park packs and the world-notable pack installed
    in the store that it can open (stores without `installed()` have none)."""
    installed = getattr(store, "installed", None)
    if installed is None:
        return []
    names, found = installed(), []
    for name in _ondemand.OPTIONAL_PACKS:
        if name in names:
            try:
                found.append(store.current(name))
            except LookupError:  # not at the pinned version: the lookup goes on without it
                continue
    return found


def _accepts(func, name):
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _plain_order(order):
    return (order,) if isinstance(order, str) else tuple(order)
