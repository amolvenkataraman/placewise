"""The pack store: reads the published index, installs packs into the data directory and looks after
them. The install procedure follows docs/pack-format.md, "Distribution": a pack is either fully in
place and verified, or not there at all.

`Store` composes the index (index.py), installing (install.py) and maintenance (maintenance.py);
this module holds what they share: settings, the on-disk layout, what's installed and the lock.
"""

import os
from pathlib import Path

from placewise.constants import store as const
from placewise.model import DataSettings

from .errors import PackNotInstalled
from .index import IndexMixin
from .install import InstallMixin
from .lock import DirLock
from .maintenance import MaintenanceMixin
from .paths import Layout, check_name, parse_pack_dir, resolve_data_dir, version_key


class Store(IndexMixin, InstallMixin, MaintenanceMixin):
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

    def _lock(self):
        return DirLock(self.layout.lock)
