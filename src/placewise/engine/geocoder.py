"""The Geocoder: a point in, the places a person would name out (placewise.model.Result).

The rules, in the order they run (constants in placewise.constants.lookup):

1. country and admin1 (_admin), with the worldview order applied;
2. country packs' boundaries: admin1 corrected by their states, provinces or PIN areas (naming);
3. GeoNames cities: the provisional city score, time zone, notable cities (_cities);
4. country packs' names: sublocality, locality, city, borough, admin2, postal, regions (naming);
5. airport, and the nearest country far offshore (_nearby);
6. parks the point is within or near, from the park packs (_within);
7. the Results and their labels (_results).

`lookup_many` runs every spatial query for all points at once and then builds the Results;
`lookup` is `lookup_many` with one point, so the two always agree.
"""

import inspect
from functools import cached_property

import numpy as np

from placewise.config import effective_worldview
from placewise.constants import lookup as const
from placewise.constants import naming as naming_const
from placewise.constants import parks as parks_const
from placewise.model import PlaceKind, Settings
from placewise.packs import Pack, open_pack

from . import _nearby, _results
from ._admin import Admin
from ._cities import Cities
from ._layers import Layers
from ._within import Parks
from .naming import Naming


class Geocoder:
    """Reverse geocoder over one or more packs. For each world layer it needs (countries, admin1,
    cities, airports) it reads the first pack that has it; a missing layer leaves its fields empty.
    Country packs (us, ca, in) name the points in their country (placewise.engine.naming).

    packs: opened Pack objects or pack directories; default: the "world" pack from the store
    (downloaded on first use unless settings.data.offline) and the country packs installed beside
    it. overrides: any object with `apply(result, lat, lon) -> Result`, applied last to every
    answer."""

    def __init__(self, packs=None, settings=None, store=None, overrides=None):
        self.settings = settings or Settings()
        if packs is None:
            if store is None:
                from placewise.store import Store

                store = Store(settings=self.settings.data)
            packs = [store.ensure(const.DEFAULT_PACK), *_installed_country_packs(store)]
        self.packs = [p if isinstance(p, Pack) else open_pack(p) for p in packs]
        if not self.packs:
            raise ValueError("a Geocoder needs at least one pack")
        self.overrides = overrides
        # placewise.overrides' engine takes relabel=; a plain `apply(result, lat, lon)` hook works too
        self._overrides_relabel = overrides is not None and _accepts(overrides.apply, "relabel")
        self.layers = Layers(self.packs)
        self.admin = Admin(self.layers)
        self.data_version = "+".join(f"{p.name}-{p.version}" for p in self.packs)

    def __repr__(self):
        return f"<Geocoder {self.data_version}>"

    @cached_property
    def cities(self):
        return Cities(self.layers, self.admin) if self.layers.has(const.CITIES) else None

    @cached_property
    def parks(self):
        """The park packs' layers (placewise.engine._within), or None when no pack has any."""
        return Parks(self.packs, self.layers, self.settings.near) or None

    @cached_property
    def naming(self):
        """The country packs' rules; they need the GeoNames cities beside them."""
        return Naming(self.packs, self.layers, self.admin, self.cities) if self.cities is not None else None

    # -- public API -------------------------------------------------------------------------------

    def lookup(self, lat, lon, *, worldview=None, near=True):
        """The Result for one point (WGS84 degrees)."""
        return self.lookup_many([lat], [lon], worldview=worldview, near=near)[0]

    def lookup_many(self, lats, lons, *, worldview=None, near=True):
        """Results for many points, one per point, in order. Vectorised: much faster per point."""
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
        a, named = self._answer(lat, lon, order, near)
        results = _results.build(self, lat, lon, a, named, order, locked)
        if self.overrides is not None:
            apply = self.overrides.apply
            extra = {"relabel": self._relabel} if self._overrides_relabel else {}
            results = [
                apply(r, x, y, **extra) for r, x, y in zip(results, lat.tolist(), lon.tolist(), strict=True)
            ]
        return results

    # -- the steps ----------------------------------------------------------------------------------

    def _answer(self, lat, lon, order, near):
        a = {}
        self.admin.answer(a, lat, lon, order)
        named = {}
        naming = self.naming
        work = naming.boundaries(a, lat, lon) if naming else ()
        if self.cities is not None:
            k_notable = max(const.NOTABLE_CANDIDATES, self.settings.near.max_near + 1)
            self.cities.answer(a, lat, lon, near, self._near_km(PlaceKind.LOCALITY), k_notable)
        if work:
            named = naming.names(a, lat, lon, work)
        if self.layers.has(const.AIRPORTS):
            _nearby.airports(a, self.layers.layer(const.AIRPORTS), lat, lon, self._near_km(PlaceKind.AIRPORT))
        _nearby.water(a, self.layers.layer(const.COUNTRIES), lat, lon)
        if self.parks is not None:
            a["parks"] = self.parks.answer(lat, lon, near)
        return a, named

    # -- worldview, settings, overrides -------------------------------------------------------------

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


def _installed_country_packs(store):
    """The country and park packs installed in the store that it can open (stores without
    `installed()` have none)."""
    installed = getattr(store, "installed", None)
    if installed is None:
        return []
    names, found = installed(), []
    for name in (*naming_const.COUNTRY_PACKS, *parks_const.PACKS):
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
