"""Packs on demand: which packs a batch of points or a search needs, and, in auto mode, fetching
them (once, under a lock, with a log line naming the pack and its size). Manual and locked modes
never download here: manual says once which pack would help, locked plans only from the cached
index and never touches the network.

The caller works out the countries (alpha-2) its points are in; the store only knows what each
pack covers (placewise.store.coverage), never what is inside a pack.
"""

import logging
import time

from placewise.constants import store as const

from ..coverage import Coverage
from ..errors import StoreError
from .index import parse_index

log = logging.getLogger("placewise.store")


class OnDemandMixin:
    """Store methods for auto mode. Needs the index and install methods, `installed`, `settings`,
    `_fetch_lock`, `_skipped` and `_plan_index_cache`."""

    @property
    def mode(self) -> str:
        """ "auto", "manual" or "locked" (DataSettings.effective_mode)."""
        return self.settings.effective_mode

    def plan(self, countries=(), extra_kinds=(), usable=None, *, everywhere=False) -> list[str]:
        """The packs not yet installed that would add to answers in `countries`: those of the kinds
        in data.auto_packs (plus `extra_kinds`, a search's own), serving one of the countries or the
        whole world, each after the packs it requires. `usable` limits them to packs the caller
        reads; `everywhere` plans for every country. Planned from the cached index unless auto mode
        may fetch a fresh one; none known means none planned."""
        index = self._plan_index()
        if index is None:
            return []
        kinds = (set(self.settings.auto_packs) | set(extra_kinds)) - {const.KIND_BASE}
        installed = self.installed()
        out = []

        def add(name, path):
            if name in out or name in installed or name in path or name not in index.packs:
                return
            for required in index.coverage[name].requires:
                add(required, (*path, name))
            out.append(name)

        for name in sorted(index.coverage):
            cov = index.coverage[name]
            if (
                cov.kind in kinds
                and (usable is None or name in usable)
                and (everywhere or cov.serves(countries))
            ):
                add(name, ())
        return out

    def pending(self, usable=None) -> set:
        """The countries (alpha-2, or "*" for world-wide) served by the packs of the auto kinds
        still missing and not given up on: points outside them can't need a fetch, and when the
        set is empty a caller needn't work out its points' countries at all."""
        index = self._plan_index()
        names = [n for n in self.plan(usable=usable, everywhere=True) if n not in self._skipped]
        return {code for n in names for code in index.coverage[n].covers}

    def wants(self, usable=None) -> bool:
        """Whether some pack of the auto kinds is missing and not given up on."""
        return any(n not in self._skipped for n in self.plan(usable=usable, everywhere=True))

    def fetch_for(self, countries=(), extra_kinds=(), usable=None) -> list:
        """In auto mode, install what `plan` names and return the new pack directories; a failed
        download is logged once and not retried by this Store. Manual and locked modes return []
        and log once per pack which one would help."""
        names = [n for n in self.plan(countries, extra_kinds, usable) if n not in self._skipped]
        if not names:
            return []
        if self.mode != const.MODE_AUTO:
            self._hint(names, countries)
            return []
        with self._fetch_lock:
            try:
                self.fetch_index()  # the archives a fresh index names; the cache may be stale
                self._plan_index_cache = self._index
            except StoreError as e:
                log.warning("placewise: couldn't refresh the pack index (%s); using the cached one", e)
            names = [n for n in self.plan(countries, extra_kinds, usable) if n not in self._skipped]
            return [path for name in names if (path := self._fetch_one(name, countries)) is not None]

    # -- helpers ----------------------------------------------------------------------------------

    def _fetch_one(self, name, countries):
        index = self._get_index()
        info, cov = index.packs[name], index.coverage.get(name, Coverage(const.KIND_OTHER))
        log.warning(
            'placewise: downloading %s %s (%s)%s; data.mode = "manual" or "locked" stops automatic downloads',
            name,
            info.version,
            _sizes(info.size_bytes, cov.installed_bytes),
            _for(cov, countries),
        )
        try:
            return self.install(name)
        except StoreError as e:
            self._skipped.add(name)
            log.warning("placewise: couldn't install %s (%s); answers go on without it", name, e)
            return None

    def _hint(self, names, countries):
        index = self._plan_index()
        for name in names:
            self._skipped.add(name)
            info, cov = index.packs[name], index.coverage[name]
            log.warning(
                "placewise: the %s pack would add detail%s (%s); data mode is %s, so it isn't "
                "downloaded: placewise data install %s",
                name,
                _for(cov, countries),
                _sizes(info.size_bytes, cov.installed_bytes),
                self.mode,
                name,
            )

    def _plan_index(self):
        """The index to plan from: the one already loaded, else the cached copy (fresh enough in
        auto mode, any age otherwise), else in auto mode a fetched one; None when none can be had."""
        if self._index is not None:
            return self._index
        if self._plan_index_cache is not None:
            return self._plan_index_cache or None
        index = self._read_cache(fresh_only=self.mode == const.MODE_AUTO)
        if index is None and self.mode == const.MODE_AUTO:
            try:
                self.fetch_index()
                index = self._index
            except StoreError as e:
                log.warning(
                    "placewise: couldn't fetch the pack index (%s); no packs are fetched automatically", e
                )
                index = self._read_cache(fresh_only=False)
        self._plan_index_cache = index if index is not None else False
        return index

    def _read_cache(self, fresh_only):
        path = self.layout.index
        try:
            if fresh_only and time.time() - path.stat().st_mtime > const.INDEX_PLAN_MAX_AGE_S:
                return None
            return parse_index(path.read_bytes(), path.as_uri())
        except (OSError, StoreError):
            return None


def human_size(n):
    """1234567 -> "1.2 MB" (decimal units, as download sizes are usually given)."""
    if n < 1000:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1000
        if n < 1000 or unit == "GB":
            return f"{n:.1f} {unit}"
    return None  # unreachable


def _sizes(archive_bytes, installed_bytes):
    text = f"{human_size(archive_bytes)} download"
    return text + (f", {human_size(installed_bytes)} on disk" if installed_bytes else "")


def _for(cov, countries):
    if cov.worldwide:
        return ""
    served = sorted(set(cov.covers) & set(countries))
    return f" for points in {', '.join(served)}" if served else ""
