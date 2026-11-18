"""The published pack index: fetching it from the index URL or a mirror, parsing it and caching it
in the data directory for offline use."""

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass, field

from placewise.constants import store as const
from placewise.model import PackInfo

from . import net
from .coverage import from_entry
from .errors import DownloadError, OfflineError, StoreError
from .paths import check_name, check_version


@dataclass(frozen=True)
class _Index:
    packs: dict = field(default_factory=dict)  # name -> PackInfo
    urls: dict = field(default_factory=dict)  # name -> absolute archive URL
    source: str = ""  # where the index came from
    coverage: dict = field(default_factory=dict)  # name -> Coverage


class IndexMixin:
    """Store methods for the index. Needs `settings`, `layout`, `index_url` and `_index`."""

    def fetch_index(self) -> dict[str, PackInfo]:
        """Download index.json from index_url, then each mirror in turn, and cache it. Offline, the
        cache is the only source."""
        if self.settings.locked:
            self._index = self._cached_index()
            return dict(self._index.packs)
        failures = []
        for url in dict.fromkeys(net.index_location(u) for u in (self.index_url, *self.settings.mirrors)):
            try:
                index = parse_index(net.fetch_bytes(url, const.INDEX_MAX_BYTES), url)
            except StoreError as e:
                failures.append(f"{url}: {e}")
                continue
            self._write_cache(index)
            self._index = index
            return dict(index.packs)
        message = "couldn't fetch the pack index: " + "; ".join(failures)
        if self.index_url == const.DEFAULT_INDEX_URL:
            message += (
                ". To use another release (a mirror or a local build), set data.index_url in"
                " placewise.toml, PLACEWISE_INDEX_URL, or --index-url"
            )
        raise DownloadError(message)

    def available(self) -> dict[str, PackInfo]:
        """The packs the index offers, by name."""
        return dict(self._get_index().packs)

    def coverage(self) -> dict:
        """What each pack the index offers covers (placewise.store.coverage.Coverage), by name."""
        return dict(self._get_index().coverage)

    def _get_index(self):
        if self._index is None:
            self.fetch_index()
        return self._index

    def _cached_index(self):
        path = self.layout.index
        if not path.is_file():
            raise OfflineError(
                f"data mode is locked (offline) and there's no cached pack index at {path}; "
                "fetch it once while online (placewise data list)"
            )
        try:
            return parse_index(path.read_bytes(), path.as_uri())
        except StoreError as e:
            raise StoreError(f"cached index {path} is damaged ({e}); fetch it again while online") from None

    def _write_cache(self, index):
        # the cached copy carries absolute URLs, so it means the same thing wherever it's read from
        doc = {
            "schema": const.INDEX_SCHEMA,
            "source": index.source,
            "packs": {
                name: {
                    **info.to_dict(),
                    "sources": list(info.sources),
                    "url": index.urls[name],
                    **index.coverage[name].to_entry(),
                }
                for name, info in index.packs.items()
            },
        }
        for entry in doc["packs"].values():
            entry.pop("name", None)
        _atomic_write(self.layout.index, json.dumps(doc, indent=1, sort_keys=True).encode())


def parse_index(data, source):
    """An _Index from index.json bytes; relative URLs resolve against `source`."""
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StoreError(f"index is not valid JSON ({e})") from None
    if not isinstance(doc, dict):
        raise StoreError("index is not a JSON object")
    if doc.get("schema") != const.INDEX_SCHEMA:
        raise StoreError(
            f"index schema {doc.get('schema')!r} isn't supported (expected {const.INDEX_SCHEMA})"
        )
    entries = doc.get("packs")
    if not isinstance(entries, dict):
        raise StoreError("index has no packs table")
    packs, urls, coverage = {}, {}, {}
    for name, entry in entries.items():
        try:
            check_name(name)
            if not isinstance(entry, dict):
                raise ValueError("not an object")
            version = check_version(_field(entry, "version", str))
            url = _field(entry, "url", str)
            sources = entry.get("sources", [])
            if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
                raise ValueError("sources must be a list of strings")
            info = PackInfo(
                name=name,
                version=version,
                schema=_field(entry, "schema", int),
                sha256=_field(entry, "sha256", str),
                size_bytes=_field(entry, "size_bytes", int),
                sources=tuple(sources),
            )
            coverage[name] = from_entry(name, entry)
        except ValueError as e:
            raise StoreError(f"index entry {name!r} is invalid: {e}") from None
        packs[name] = info
        urls[name] = net.resolve(source, url)
    return _Index(packs, urls, source, coverage)


def _field(entry, key, kind):
    value = entry.get(key)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise ValueError(f"{key} must be a {kind.__name__}")
    return value


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=const.TEMP_PREFIX, dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
