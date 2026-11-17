"""An inter-process lock on the data directory, built on O_CREAT | O_EXCL so it works on every OS and
filesystem without fcntl or msvcrt."""

import contextlib
import os
import time

from placewise.constants import store as const

from .errors import LockError


class DirLock:
    """Context manager. While held, call `touch()` during long work so others don't think it's stale."""

    def __init__(self, path):
        self.path = path
        self._token = None
        self._last_touch = 0.0

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + const.LOCK_WAIT_S
        # the token lets release tell our lock from one another process took after breaking ours
        token = f"{os.getpid()} {os.urandom(8).hex()}\n"
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if self._break_if_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise LockError(
                        f"another placewise process is using the data directory (lock file {self.path}); "
                        "if none is running, delete that file"
                    ) from None
                time.sleep(const.LOCK_POLL_S)
                continue
            with os.fdopen(fd, "w") as f:
                f.write(token)
            self._token = token
            self._last_touch = time.monotonic()
            return self

    def touch(self):
        now = time.monotonic()
        if self._token and now - self._last_touch >= const.LOCK_HEARTBEAT_S:
            self._last_touch = now
            with contextlib.suppress(OSError):
                os.utime(self.path)

    def __exit__(self, *exc):
        try:
            with open(self.path) as f:
                ours = f.read() == self._token
        except OSError:
            ours = False
        if ours:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self.path)
        self._token = None

    def _break_if_stale(self):
        """True if the lock is gone (or was stale and is now removed), so acquiring should be retried."""
        try:
            age = time.time() - os.stat(self.path).st_mtime
        except FileNotFoundError:
            return True
        if age < const.LOCK_STALE_S:
            return False
        # Two waiters can both see the same stale lock; O_EXCL still lets only one of them create the
        # next one. The remaining window (unlinking a lock created a moment ago) needs a holder that
        # died more than LOCK_STALE_S ago racing two newcomers, and costs one redundant install at worst.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.path)
        return True
