"""Location search with packs: a `Gazetteer` (placewise.text) over forward search, so
`parse_location` confirms cities and returns their places (point, box, id) when packs are open.

    from placewise.text import parse_location
    parse_location("Hybrid - Mississauga, ON", SearchGazetteer())   # part.place.point ...
"""

from placewise.constants import search as const
from placewise.constants._keys import city_key

_CITY_KINDS = ("locality", "sublocality", "borough")


class SearchGazetteer:
    """`match(city, country_iso2, admin1_code) -> Place | None`: the most prominent settlement of
    exactly that name (or alias) in that country and admin1. `search` is a Search or a Geocoder;
    default: the default Geocoder's. Answers are cached (location strings repeat)."""

    def __init__(self, search=None, cache_size=const.REVERSE_CACHE_SIZE):
        if search is not None and not hasattr(search, "context"):
            search = search.search  # a Geocoder
        self._search = search
        self._cache = {}
        self._size = cache_size

    @property
    def search(self):
        if self._search is None:
            from placewise.engine import default_geocoder

            self._search = default_geocoder().search
        return self._search

    def match(self, city, country_iso2=None, admin1_code=None):
        k = (city_key(city), country_iso2, admin1_code)
        found = self._cache.get(k, _MISSING)  # one read: another thread may clear the cache
        if found is not _MISSING:
            return found
        admin1 = f"{country_iso2}-{admin1_code}" if country_iso2 and admin1_code else None
        try:
            found = self.search.find(city, limit=1, country=country_iso2, admin1=admin1, kinds=_CITY_KINDS)
        except ValueError:  # a code the tables don't know: no confirmation
            found = []
        place = None
        if found:
            p = found[0].place
            if k[0] in {city_key(p.name), *(city_key(a) for a in p.aliases)} or k[0] in _alias_keys(found[0]):
                place = p
        if len(self._cache) >= self._size:
            self._cache.clear()
        self._cache[k] = place
        return place


_MISSING = object()


def _alias_keys(entity):
    return {city_key(a.name) for a in entity.alternates}
