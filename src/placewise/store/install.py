"""Installing packs: download, verify, unpack and move into place atomically (docs/pack-format.md,
"Distribution"), plus ensure-on-first-use and updates from the index."""

import contextlib
import os
import shutil
import tempfile
import time
from pathlib import Path

from placewise.constants import store as const

from . import archive, net
from .errors import IntegrityError, OfflineError, PackNotInstalled, StoreError, UnsupportedSchemaError
from .paths import check_name, check_version, version_key


class InstallMixin:
    """Store methods that put packs on disk. Needs the index methods, `installed`, `current` and
    `_lock`."""

    def ensure(self, name, *, progress=None) -> Path:
        """The current version, installing it first if needed (and allowed): what lookups call."""
        try:
            return self.current(name)
        except PackNotInstalled as e:
            if self.settings.locked:
                raise PackNotInstalled(
                    name, e.version, pinned=bool(self.settings.pin), offline=True
                ) from None
        return self.install(name, self.settings.pin, progress=progress)

    def install(self, name, version=None, *, progress=None, _requiring=()) -> Path:
        """Install `name` (the index's version, or `version`, which must be the one the index offers),
        after any pack it requires (index.json `requires`) that isn't installed yet. A version that's
        already installed and verifies is left alone. `progress(done, total)` is called with byte
        counts during the download."""
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
        coverage = index.coverage.get(name)
        for required in coverage.requires if coverage is not None else ():
            if required not in (name, *_requiring) and required not in self.installed():
                self.install(required, progress=progress, _requiring=(*_requiring, name))
        with self._lock() as lock:
            if self._intact(name, info.version):  # another process may have just installed it
                return self.layout.pack(name, info.version)
            if self.settings.locked:
                raise OfflineError(_locked(f"{name} {info.version} can't be downloaded"))
            self._clean_temp()
            return self._install_locked(info, index.urls[name], progress, lock)

    def update(self, names=None, *, progress=None) -> list[tuple[str, str | None, str]]:
        """Install newer versions from the index for `names` (default: every installed pack). Never
        deletes; a pack held by DataSettings.pin is left alone. Returns (name, old, new) per change."""
        if self.settings.locked:
            raise OfflineError(_locked("updating needs the network"))
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


def _locked(what):
    return (
        f"data mode is locked (offline), so {what}; to allow downloads, run "
        "`placewise data mode manual` (and drop --offline or data.offline if set)"
    )
