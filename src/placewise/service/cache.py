"""An LRU result cache in front of any geocoder, keyed on coordinates rounded to ~1 m plus worldview."""

import dataclasses
import threading
from collections import OrderedDict

from placewise.constants import server as const


def _worldview_key(worldview):
    if worldview is None:
        return None
    if isinstance(worldview, str):
        return tuple(p.strip() for p in worldview.split(",") if p.strip())
    return tuple(worldview)


class CachedGeocoder:
    """Wraps a geocoder (lookup / lookup_many / data_version / settings) with a thread-safe LRU.

    Points in the same 1e-5 degree cell share an answer (the place names don't change within a
    metre); a hit is returned with the caller's own lat/lon. With the operator's worldview lock on,
    the requested worldview is ignored by the engine, so it isn't part of the key either."""

    def __init__(self, geocoder, size=const.DEFAULT_CACHE_SIZE, *, decimals=const.CACHE_DECIMALS):
        if size < 0:
            raise ValueError("cache size can't be negative")
        self.geocoder = geocoder
        self.max_size = int(size)
        self.decimals = decimals
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self._hits = self._misses = 0

    @property
    def data_version(self):
        return self.geocoder.data_version

    @property
    def settings(self):
        return self.geocoder.settings

    def cache_info(self):
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._entries),
                "max_size": self.max_size,
            }

    def clear(self):
        with self._lock:
            self._entries.clear()

    def _key(self, lat, lon, worldview):
        settings = getattr(self.geocoder, "settings", None)
        locked = bool(getattr(getattr(settings, "worldview", None), "lock", False))
        # + 0.0 folds -0.0 into 0.0 so both land on one key
        return (
            round(lat, self.decimals) + 0.0,
            round(lon, self.decimals) + 0.0,
            None if locked else _worldview_key(worldview),
        )

    def _get(self, key):
        with self._lock:
            result = self._entries.get(key)
            if result is None:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return result

    def _put(self, key, result):
        if not self.max_size:
            return
        with self._lock:
            self._entries[key] = result
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)

    @staticmethod
    def _echo(result, lat, lon):
        if result.lat == lat and result.lon == lon:
            return result
        return dataclasses.replace(result, lat=lat, lon=lon)

    def lookup(self, lat, lon, *, worldview=None):
        lat, lon = float(lat), float(lon)
        key = self._key(lat, lon, worldview)
        cached = self._get(key)
        if cached is not None:
            return self._echo(cached, lat, lon)
        result = self.geocoder.lookup(lat, lon, worldview=worldview)
        self._put(key, result)
        return result

    def lookup_many(self, lats, lons, *, worldview=None):
        lats, lons = [float(v) for v in lats], [float(v) for v in lons]
        if len(lats) != len(lons):
            raise ValueError("lats and lons must be the same length")
        out = [None] * len(lats)
        missing = {}  # key -> indexes needing it, so duplicate points are fetched once
        for i, (lat, lon) in enumerate(zip(lats, lons, strict=True)):
            key = self._key(lat, lon, worldview)
            cached = self._get(key) if key not in missing else None
            if cached is not None:
                out[i] = self._echo(cached, lat, lon)
            else:
                missing.setdefault(key, []).append(i)
        if missing:
            firsts = [idx[0] for idx in missing.values()]
            fetched = self.geocoder.lookup_many(
                [lats[i] for i in firsts], [lons[i] for i in firsts], worldview=worldview
            )
            for (key, indexes), result in zip(missing.items(), fetched, strict=True):
                self._put(key, result)
                for i in indexes:
                    out[i] = self._echo(result, lats[i], lons[i])
        return out
