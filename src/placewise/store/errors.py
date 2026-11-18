"""Store errors. Messages are written for the person at the terminal: what went wrong and what to run."""


class StoreError(Exception):
    """Base class: anything the store refuses or can't do."""


class PackNotInstalled(StoreError, LookupError):  # noqa: N818 - reads better at call sites
    def __init__(self, name, version=None, *, pinned=False, offline=False, hint=True):
        self.name, self.version = name, version
        what = f"pack {name!r}" + (f" version {version}" if version else "") + (" (pinned)" if pinned else "")
        message = f"{what} isn't installed"
        if hint:
            command = f"placewise data install {name}" + (f" --version {version}" if version else "")
            message += f"; install it with: {command}"
        if offline:
            message += " (data mode is locked, or offline, so it won't be downloaded automatically)"
        super().__init__(message)


class OfflineError(StoreError):
    """The operation needs the network and the data mode is locked (DataSettings.mode, or offline)."""


class IntegrityError(StoreError):
    """A download or an installed pack doesn't match its checksums, or its archive is unsafe."""


class DownloadError(StoreError):
    """A URL couldn't be fetched, or sent more than it should have."""


class UnsupportedSchemaError(StoreError):
    """A pack or index uses a format version this placewise can't read."""


class LockError(StoreError):
    """Another process is working in the data directory."""
