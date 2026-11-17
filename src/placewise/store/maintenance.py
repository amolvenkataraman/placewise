"""Looking after installed packs: re-verifying them, pruning old versions and removing packs."""

import os
import shutil
import tempfile
from pathlib import Path

from placewise.constants import store as const

from . import archive
from .errors import PackNotInstalled, StoreError
from .paths import check_name, check_version


class MaintenanceMixin:
    """Store methods that check and delete installed packs. Needs `installed` and `_lock`."""

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
