"""Pack storage: finding, downloading, verifying and housekeeping data packs on disk.

store = Store()               # data dir and index URL from settings, env or platform defaults
path = store.ensure("world")  # the pack directory, downloaded on first use unless offline
"""

from .errors import (
    DownloadError,
    IntegrityError,
    LockError,
    OfflineError,
    PackNotInstalled,
    StoreError,
    UnsupportedSchemaError,
)
from .paths import Layout, resolve_data_dir
from .store import Store

__all__ = [
    "DownloadError",
    "IntegrityError",
    "Layout",
    "LockError",
    "OfflineError",
    "PackNotInstalled",
    "Store",
    "StoreError",
    "UnsupportedSchemaError",
    "resolve_data_dir",
]
