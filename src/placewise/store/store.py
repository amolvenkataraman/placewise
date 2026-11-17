"""The pack store: reads the published index, installs packs into the data directory and looks after
them. The install procedure follows docs/pack-format.md, "Distribution": a pack is either fully in
place and verified, or not there at all.
"""

import contextlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from placewise.constants import store as const
from placewise.model import DataSettings, PackInfo

from . import archive, net
from .errors import (
    DownloadError,
    IntegrityError,
    OfflineError,
    PackNotInstalled,
    StoreError,
    UnsupportedSchemaError,
)
from .lock import DirLock
from .paths import Layout, check_name, check_version, parse_pack_dir, resolve_data_dir, version_key


@dataclass(frozen=True)
class _Index:
    packs: dict = field(default_factory=dict)  # name -> PackInfo
    urls: dict = field(default_factory=dict)  # name -> absolute archive URL
    source: str = ""  # where the index came from


class Store:
    """Packs on disk under `<data_dir>/packs/<name>-<version>/`, fed from an index of releases.

    data_dir: overrides DataSettings.data_dir, $PLACEWISE_DATA_DIR and the platform default.
    index_url: overrides DataSettings.index_url, $PLACEWISE_INDEX_URL and the published default.
    """

    def __init__(self, data_dir=None, settings: DataSettings | None = None, index_url=None):
        self.settings = settings or DataSettings()
        self.layout = Layout(resolve_data_dir(data_dir, self.settings))
        self.index_url = (
            index_url
            or self.settings.index_url
            or os.environ.get(const.ENV_INDEX_URL)
            or const.DEFAULT_INDEX_URL
        )
        self._index = None

    @property
    def data_dir(self) -> Path:
        return self.layout.root

    def __repr__(self):
        return f"Store({str(self.data_dir)!r}, index_url={self.index_url!r})"

    # -- index ------------------------------------------------------------------------------------

    def fetch_index(self) -> dict[str, PackInfo]:
        """Download index.json from index_url, then each mirror in turn, and cache it. Offline, the
        cache is the only source."""
        if self.settings.offline:
            self._index = self._cached_index()
            return dict(self._index.packs)
        failures = []
        for url in dict.fromkeys(net.index_location(u) for u in (self.index_url, *self.settings.mirrors)):
            try:
                index = _parse_index(net.fetch_bytes(url, const.INDEX_MAX_BYTES), url)
            except StoreError as e:
                failures.append(f"{url}: {e}")
                continue
            self._write_cache(index)
            self._index = index
            return dict(index.packs)
        raise DownloadError("couldn't fetch the pack index: " + "; ".join(failures))

    def available(self) -> dict[str, PackInfo]:
        """The packs the index offers, by name."""
        return dict(self._get_index().packs)

    def _get_index(self):
        if self._index is None:
            self.fetch_index()
        return self._index

    def _cached_index(self):
        path = self.layout.index
        if not path.is_file():
            raise OfflineError(
                f"offline mode is on and there's no cached pack index at {path}; "
                "fetch it once while online (placewise data list)"
            )
        try:
            return _parse_index(path.read_bytes(), path.as_uri())
        except StoreError as e:
            raise StoreError(f"cached index {path} is damaged ({e}); fetch it again while online") from None

    def _write_cache(self, index):
        # the cached copy carries absolute URLs, so it means the same thing wherever it's read from
        doc = {
            "schema": const.INDEX_SCHEMA,
            "source": index.source,
            "packs": {
                name: {**info.to_dict(), "sources": list(info.sources), "url": index.urls[name]}
                for name, info in index.packs.items()
            },
        }
        for entry in doc["packs"].values():
            entry.pop("name", None)
        _atomic_write(self.layout.index, json.dumps(doc, indent=1, sort_keys=True).encode())

    # -- what's installed -------------------------------------------------------------------------

    def installed(self) -> dict[str, list[str]]:
        """Installed versions per pack, oldest first."""
        found = {}
        if not self.layout.packs.is_dir():
            return found
        with os.scandir(self.layout.packs) as entries:
            for entry in entries:
                # temp dirs start with a dot; a symlink isn't something install created
                if entry.name.startswith(".") or not entry.is_dir(follow_symlinks=False):
                    continue
                if parsed := parse_pack_dir(entry.name):
                    found.setdefault(parsed[0], []).append(parsed[1])
        return {name: sorted(versions, key=version_key) for name, versions in sorted(found.items())}

    def current(self, name) -> Path:
        """The installed version to read: the pinned one if DataSettings.pin is set, else the newest."""
        check_name(name)
        versions = self.installed().get(name, [])
        pin = self.settings.pin
        if pin:
            if pin not in versions:
                raise PackNotInstalled(name, pin, pinned=True)
            return self.layout.pack(name, pin)
        if not versions:
            raise PackNotInstalled(name)
        return self.layout.pack(name, versions[-1])

    def ensure(self, name, *, progress=None) -> Path:
        """The current version, installing it first if needed (and allowed): what lookups call."""
        try:
            return self.current(name)
        except PackNotInstalled as e:
            if self.settings.offline:
                raise PackNotInstalled(
                    name, e.version, pinned=bool(self.settings.pin), offline=True
                ) from None
        return self.install(name, self.settings.pin, progress=progress)

    # -- install ----------------------------------------------------------------------------------

    def install(self, name, version=None, *, progress=None) -> Path:
        """Install `name` (the index's version, or `version`, which must be the one the index offers).
        A version that's already installed and verifies is left alone. `progress(done, total)` is
        called with byte counts during the download."""
        check_name(name)
        if version is not None:
            check_version(version)
            if self._intact(name, version):
                return self.layout.pack(name, version)
        index = self._get_index()
        info = index.packs.get(name)
        if info is None:
            offered = ", ".join(sorted(index.packs)) or "none"
            raise StoreError(f"the index has no pack named {name!r} (available: {offered})")
        if version is not None and version != info.version:
            raise StoreError(f"the index offers {name} {info.version}, not {version}")
        if info.schema != const.PACK_SCHEMA:
            raise UnsupportedSchemaError(
                f"{name} {info.version} uses pack schema {info.schema}, but this placewise reads schema "
                f"{const.PACK_SCHEMA}; upgrade placewise to use it"
            )
        with self._lock() as lock:
            if self._intact(name, info.version):  # another process may have just installed it
                return self.layout.pack(name, info.version)
            if self.settings.offline:
                raise OfflineError(f"offline mode is on, so {name} {info.version} can't be downloaded")
            self._clean_temp()
            return self._install_locked(info, index.urls[name], progress, lock)

    def _install_locked(self, info, url, progress, lock):
        top = f"{info.name}-{info.version}"
        self.layout.packs.mkdir(parents=True, exist_ok=True)
        # inside packs/ so the final rename stays on one filesystem and is atomic
        work = Path(tempfile.mkdtemp(prefix=const.TEMP_PREFIX, dir=self.layout.packs))
        try:
            download = work / "download.tar.xz"
            digest = net.fetch_file(
                url,
                download,
                expected_size=info.size_bytes,
                limit=info.size_bytes + const.DOWNLOAD_SLACK_BYTES,
                progress=progress,
                heartbeat=lock.touch,
            )
            if digest != info.sha256:
                raise IntegrityError(
                    f"{top}: archive sha256 {digest} doesn't match the index ({info.sha256})"
                )
            unpacked = work / "unpacked"
            unpacked.mkdir()
            archive.safe_extract(download, unpacked, top, archive.unpack_limit(info.size_bytes))
            download.unlink()
            staged = unpacked / top
            if not staged.is_dir():
                raise IntegrityError(f"{top}: the archive has no {top}/ directory")
            if problems := archive.check_pack_dir(staged, info.name, info.version, "the index"):
                more = f" (and {len(problems) - 3} more)" if len(problems) > 3 else ""
                raise IntegrityError(f"{top}: " + "; ".join(problems[:3]) + more)
            target = self.layout.pack(info.name, info.version)
            if os.path.lexists(target):  # a damaged copy: set it aside, it's deleted with `work`
                os.rename(target, work / "damaged")
            os.rename(staged, target)
            return target
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _intact(self, name, version):
        path = self.layout.pack(name, version)
        return (
            not path.is_symlink()
            and path.is_dir()
            and not archive.check_pack_dir(path, name, version, "its directory name")
        )

    # -- maintenance ------------------------------------------------------------------------------

    def update(self, names=None, *, progress=None) -> list[tuple[str, str | None, str]]:
        """Install newer versions from the index for `names` (default: every installed pack). Never
        deletes; a pack held by DataSettings.pin is left alone. Returns (name, old, new) per change."""
        if self.settings.offline:
            raise OfflineError("offline mode is on, and updating needs the network")
        index = self.fetch_index()
        installed = self.installed()
        changes = []
        for name in names or list(installed):
            check_name(name)
            have = installed.get(name, [])
            if self.settings.pin and self.settings.pin in have:
                continue
            info = index.get(name)
            if info is None:
                if names:
                    raise StoreError(f"the index has no pack named {name!r}")
                continue  # retired from the index; what's installed keeps working
            old = have[-1] if have else None
            if old and version_key(info.version) <= version_key(old):
                continue
            self.install(name, info.version, progress=progress)
            changes.append((name, old, info.version))
        return changes

    def verify(self, name=None) -> list[str]:
        """Re-hash installed packs (all, or every version of `name`); one line per problem found."""
        installed = self.installed()
        if name is not None:
            check_name(name)
            if name not in installed:
                raise PackNotInstalled(name)
            installed = {name: installed[name]}
        problems = []
        for pack, versions in installed.items():
            for version in versions:
                path = self.layout.pack(pack, version)
                found = archive.check_pack_dir(path, pack, version, "its directory name")
                problems += [f"{path.name}: {p}" for p in found]
        return problems

    def prune(self, keep=1) -> list[tuple[str, str]]:
        """Delete all but the newest `keep` versions of each pack, never the pinned or current one."""
        if keep < 1:
            raise ValueError("prune keeps at least one version")
        removed = []
        with self._lock():
            for name, versions in self.installed().items():
                spare = set(versions[-keep:])
                if self.settings.pin:
                    spare.add(self.settings.pin)
                for version in versions:
                    if version not in spare:
                        self._delete(name, version)
                        removed.append((name, version))
        return removed

    def remove(self, name, version=None) -> list[str]:
        """Delete one installed version of a pack, or every version. Returns the versions removed."""
        check_name(name)
        if version is not None:
            check_version(version)
        with self._lock():
            versions = self.installed().get(name, [])
            targets = [version] if version is not None else versions
            if not targets or not set(targets) <= set(versions):
                raise PackNotInstalled(name, version, hint=False)
            for v in targets:
                self._delete(name, v)
        return targets

    def _delete(self, name, version):
        path = self.layout.pack(name, version)  # validated name and version: no separators, no ..
        packs = self.layout.packs.resolve()
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != packs:
            raise StoreError(f"refusing to delete {path}: not a pack directory inside {packs}")
        # renamed first, so an interrupted delete leaves a temp dir, not a half-pack that looks installed
        doomed = Path(tempfile.mkdtemp(prefix=const.TEMP_PREFIX, dir=packs)) / "doomed"
        os.rename(path, doomed)
        shutil.rmtree(doomed.parent)

    def _lock(self):
        return DirLock(self.layout.lock)

    def _clean_temp(self):
        """Remove temp dirs that crashed installs left behind. Called with the lock held."""
        if not self.layout.packs.is_dir():
            return
        cutoff = time.time() - const.LOCK_STALE_S
        for entry in self.layout.packs.iterdir():
            if entry.name.startswith(const.TEMP_PREFIX) and not entry.is_symlink() and entry.is_dir():
                with contextlib.suppress(OSError):
                    if entry.stat().st_mtime < cutoff:
                        shutil.rmtree(entry)


def _parse_index(data, source):
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
    packs, urls = {}, {}
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
        except ValueError as e:
            raise StoreError(f"index entry {name!r} is invalid: {e}") from None
        packs[name] = info
        urls[name] = net.resolve(source, url)
    return _Index(packs, urls, source)


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
