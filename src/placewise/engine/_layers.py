"""The layers a Geocoder reads and the Places made from their rows.

A layer is known by its key, "<pack>/<layer>" ("world/cities", "usa/places"), which is also how
Result.sources names it ("usa/places:polygon"). The world layers have fixed roles (countries,
admin1, cities, airports: the first pack that has each); country packs register their own layers
with the naming rules that read them (placewise.engine.naming).
"""

from placewise.constants import lookup as const
from placewise.constants.countries import BY_ALPHA2
from placewise.constants.countries import lookup as country_code
from placewise.model import Place, PlaceKind, Point

WORLD_ROLES = (const.COUNTRIES, const.ADMIN1, const.CITIES, const.AIRPORTS)


class Layers:
    def __init__(self, packs):
        self.packs = packs
        self._by_key = {}
        self._world = {}
        for role in WORLD_ROLES:
            pack = next((p for p in packs if role in p), None)
            if pack is not None:
                self._world[role] = self.add(pack, role)
        self._places = {}
        self._columns = {}
        self._makers = {}

    # -- layers -------------------------------------------------------------------------------------

    def add(self, pack, name, maker=None):
        """Register pack[name]; returns its key. `maker(get, layer, row)` builds its Places."""
        key = f"{pack.name}/{name}"
        self._by_key[key] = pack[name]
        if maker is not None:
            self._makers[key] = maker
        return key

    def world(self, role):
        """The key of a world role's layer, or None when no pack has it."""
        return self._world.get(role)

    def has(self, role):
        return role in self._world

    def layer(self, key_or_role):
        """A layer by key, or a world layer by role; None when absent."""
        key = self._world.get(key_or_role, key_or_role)
        return self._by_key.get(key)

    def source(self, key_or_role, rule):
        key = self._world.get(key_or_role, key_or_role)
        return f"{key}:{rule}"

    def column(self, key_or_role, field):
        """A string column as a plain list (cached), or None when the layer lacks the field."""
        key = self._world.get(key_or_role, key_or_role)
        cache_key = (key, field)
        if cache_key not in self._columns:
            layer = self._by_key[key]
            self._columns[cache_key] = layer.column(field).tolist() if field in layer.fields else None
        return self._columns[cache_key]

    # -- places -------------------------------------------------------------------------------------

    def place(self, key_or_role, row):
        key = self._world.get(key_or_role, key_or_role)
        cache = self._places.get(key)
        if cache is None:
            cache = self._places[key] = {}
        place = cache.get(row)
        if place is None:
            place = cache[row] = self._make(key, row)
        return place

    def cache(self, key_or_role):
        """The {row: Place} cache of a layer, for loops that read it directly (fill with place())."""
        key = self._world.get(key_or_role, key_or_role)
        return self._places.setdefault(key, {})

    def _make(self, key, row):
        layer = self._by_key[key]

        def get(field):
            values = self.column(key, field)
            return values[row] if values is not None else ""

        maker = self._makers.get(key)
        if maker is not None:
            return maker(get, layer, row)
        role = next((r for r, k in self._world.items() if k == key), None)
        return _WORLD_MAKERS[role](get, layer, row)


def codes(get, *fields):
    """{field: value} for the fields with a value."""
    return {f: get(f) for f in fields if get(f)}


def source_of(layer):
    return layer.sources[0] if layer.sources else None


def _country(get, layer, i):
    pid, name, iso2 = get("id"), get("name") or get("id"), get("iso2")
    aliases = ()
    # Natural Earth's long forms ("United States of America") give way to the ISO short name, when
    # they are a name of that very country (not "Coral Sea Islands", which shares AU)
    if iso2 in BY_ALPHA2 and BY_ALPHA2[iso2].name != name and country_code(name) == iso2:
        name, aliases = BY_ALPHA2[iso2].name, (name,)
    return Place(
        pid, name, PlaceKind.COUNTRY, bbox=layer.bbox(i), codes=codes(get, "iso2", "iso3"), aliases=aliases,
        source=source_of(layer),
    )  # fmt: skip


def _admin1(get, layer, i):
    pid = get("id")
    found = {"iso": pid[4:]} if pid.startswith("iso:") else {}
    found.update(codes(get, "country"))
    return Place(
        pid, get("name") or pid, PlaceKind.ADMIN1, bbox=layer.bbox(i), codes=found, source=source_of(layer)
    )


def _city(get, layer, i):
    point = Point(float(layer.lat[i]), float(layer.lon[i]))
    return Place(
        get("id"), get("name") or get("id"), PlaceKind.LOCALITY, point=point, codes=codes(get, "country"),
        source=source_of(layer),
    )  # fmt: skip


def _airport(get, layer, i):
    point = Point(float(layer.lat[i]), float(layer.lon[i]))
    found = codes(get, "iata", "icao", "country", "region")
    return Place(
        get("id"),
        get("name") or get("id"),
        PlaceKind.AIRPORT,
        point=point,
        codes=found,
        source=source_of(layer),
    )


_WORLD_MAKERS = {
    const.COUNTRIES: _country,
    const.ADMIN1: _admin1,
    const.CITIES: _city,
    const.AIRPORTS: _airport,
}
