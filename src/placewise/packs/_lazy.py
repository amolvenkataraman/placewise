"""Lazy state that threads can share: one Geocoder (and its packs) serves concurrent lookups, as the
threaded HTTP server does, so a cache built on first use must never be seen half built.

- `once` is functools.cached_property computed at most once per object, even when threads ask for
  it together (since Python 3.12 cached_property has no lock: two threads would each build a
  boundary index, gigabytes at a time). After the first build the value sits in the object's
  __dict__ and is read with no lock at all.
- `Guarded` gives an object that grows in place (slabs, fine grids, edge caps) a reentrant lock to
  hold across each change and each read of what it changes; the lock is not pickled. Code holding
  such a lock never builds a `once` value (a build may wait on that lock: no deadlock either way).
"""

import threading

# Builds are rare (once per object and attribute), so one reentrant lock for all of them is enough;
# reentrant because one build may need another (the slabs need the geometry).
_BUILD = threading.RLock()


class once:  # noqa: N801 - used as a decorator, like functools.cached_property
    """functools.cached_property, built at most once per object across threads."""

    def __init__(self, func):
        self.func = func
        self.name = func.__name__
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        cache = obj.__dict__
        try:
            return cache[self.name]
        except KeyError:
            pass
        with _BUILD:
            try:
                return cache[self.name]
            except KeyError:
                value = cache[self.name] = self.func(obj)
                return value


class Guarded:
    """A mixin: self._lock, a reentrant lock that pickling leaves out and unpickling remakes."""

    def __init__(self):
        self._lock = threading.RLock()

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock = threading.RLock()
