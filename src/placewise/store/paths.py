"""Where placewise keeps its data, and the layout inside that directory."""

import os
import re
from pathlib import Path

from placewise.constants import store as const

_NAME = re.compile(const.PACK_NAME_PATTERN)
_VERSION = re.compile(const.PACK_VERSION_PATTERN)
# non-greedy name: "us-nature-2026.11" splits at the last hyphen that starts a version
_PACK_DIR = re.compile(rf"({const.PACK_NAME_PATTERN}?)-({const.PACK_VERSION_PATTERN})")


def resolve_data_dir(explicit=None, settings=None):
    """The data directory: an explicit argument, then DataSettings.data_dir, then $PLACEWISE_DATA_DIR,
    then ~/.placewise on every platform (one place to find, back up or delete everything placewise
    downloads)."""
    for candidate in (explicit, settings.data_dir if settings else None, os.environ.get(const.ENV_DATA_DIR)):
        if candidate:
            return Path(candidate).expanduser()
    return Path.home() / const.DEFAULT_DATA_DIR


def check_name(name):
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"invalid pack name {name!r}: lowercase letters, digits and hyphens only")
    return name


def check_version(version):
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ValueError(f"invalid pack version {version!r}: expected YYYY.MM or YYYY.MM.N")
    return version


def version_key(version):
    """Sort key: "2026.10.10" is newer than "2026.10.2", which plain string order gets wrong."""
    return tuple(int(part) for part in version.split("."))


def parse_pack_dir(dirname):
    """("us-nature", "2026.11") for "us-nature-2026.11"; None for anything that isn't a pack directory."""
    match = _PACK_DIR.fullmatch(dirname)
    return (match.group(1), match.group(2)) if match else None


class Layout:
    """Paths inside a data directory. Pack paths are built only from validated names, so a name can
    never point outside packs/."""

    __slots__ = ("root",)

    def __init__(self, root):
        self.root = Path(root)

    @property
    def packs(self):
        return self.root / const.PACKS_DIR

    @property
    def index(self):
        return self.root / const.INDEX_CACHE

    @property
    def overrides(self):
        return self.root / const.OVERRIDES_FILE

    @property
    def lock(self):
        return self.root / const.LOCK_FILE

    def pack(self, name, version):
        return self.packs / f"{check_name(name)}-{check_version(version)}"

    def __repr__(self):
        return f"Layout({str(self.root)!r})"
