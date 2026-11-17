"""API keys: random tokens shown once, stored only as SHA-256 hashes in a private JSON file.

A key is `pw_` plus 32 random bytes (URL-safe base64). With that much randomness an unsalted SHA-256
is enough: nobody can brute-force the hash back to a key, and a stolen keys file grants nothing.
Checks compare the hash of the presented key against every stored hash with `hmac.compare_digest`
(constant time per comparison, and no early exit across keys), so timing reveals nothing.

The server re-reads the file whenever it changes on disk, so `placewise server keys revoke` takes
effect on a running server without a restart.
"""

import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from placewise.constants import server as const
from placewise.constants import store as store_const
from placewise.model._base import Model


@dataclass(frozen=True, slots=True)
class ApiKey(Model):
    """One stored key. `hash` is the hex SHA-256 of the full token; the token itself is never kept."""

    id: str
    hash: str
    label: str = ""
    created: str = ""  # ISO 8601, UTC
    rate_limit: int = const.DEFAULT_KEY_RATE_PER_MIN  # requests per minute; 0 means unlimited

    def __post_init__(self):
        if not self.id or len(self.hash) != 64:
            raise ValueError("a key needs an id and a 64-character SHA-256 hex hash")
        if not isinstance(self.rate_limit, int) or isinstance(self.rate_limit, bool) or self.rate_limit < 0:
            raise ValueError("rate_limit is requests per minute: a whole number, 0 for unlimited")

    def public(self):
        """Everything but the hash, for listings."""
        return {"id": self.id, "label": self.label, "created": self.created, "rate_limit": self.rate_limit}


def hash_key(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def default_keys_path():
    """$PLACEWISE_KEYS_FILE, else server-keys.json in the per-user config directory. Keys live apart
    from the data directory, which a hosted server should mount read-only."""
    explicit = os.environ.get(const.ENV_KEYS_FILE)
    if explicit:
        return Path(explicit).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        root = Path(xdg) if xdg and os.path.isabs(xdg) else Path.home() / ".config"
    return root / store_const.APP_DIR_NAME / const.KEYS_FILENAME


class KeyStore:
    """The keys file. Safe to share between threads; several processes may read while one writes
    (writes replace the file atomically)."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_keys_path()
        self._lock = threading.Lock()
        self._keys = []
        self._stamp = None  # (mtime_ns, size, inode) of the version loaded, or "missing"

    def __repr__(self):
        return f"KeyStore({str(self.path)!r})"

    # -- reading -----------------------------------------------------------------------------------

    def list(self):
        with self._lock:
            self._refresh()
            return list(self._keys)

    def verify(self, token):
        """The ApiKey a presented token belongs to, or None."""
        if not isinstance(token, str) or not token or len(token) > const.MAX_KEY_CHARS:
            return None
        digest = hash_key(token)
        with self._lock:
            self._refresh()
            keys = self._keys
        match = None
        for key in keys:  # compare against all of them; no early exit
            if hmac.compare_digest(digest, key.hash):
                match = key
        return match

    def _refresh(self):
        try:
            st = os.stat(self.path)
            stamp = (st.st_mtime_ns, st.st_size, st.st_ino)
        except FileNotFoundError:
            stamp = "missing"
        if stamp == self._stamp:
            return
        self._keys = self._read() if stamp != "missing" else []
        self._stamp = stamp

    def _read(self):
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict) or not isinstance(doc.get("keys"), list):
                raise ValueError('expected {"version": 1, "keys": [...]}')
            if doc.get("version") != const.KEYS_FILE_VERSION:
                raise ValueError(f"unsupported keys file version {doc.get('version')!r}")
            return [ApiKey.from_dict(entry) for entry in doc["keys"]]
        except (ValueError, TypeError) as e:
            raise ValueError(f"keys file {self.path} is malformed: {e}") from None

    # -- writing -----------------------------------------------------------------------------------

    def add(self, label="", rate_limit=const.DEFAULT_KEY_RATE_PER_MIN):
        """Create a key; returns (ApiKey, token). The token is shown this once and never stored."""
        token = const.KEY_PREFIX + secrets.token_urlsafe(const.KEY_BYTES)
        created = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        with self._lock:
            keys = self._load_for_write()
            taken = {k.id for k in keys}
            key_id = secrets.token_hex(const.KEY_ID_BYTES)
            while key_id in taken:
                key_id = secrets.token_hex(const.KEY_ID_BYTES)
            record = ApiKey(
                id=key_id, hash=hash_key(token), label=label, created=created, rate_limit=rate_limit
            )
            self._write([*keys, record])
        return record, token

    def revoke(self, key_id):
        """Delete a key by id; ValueError if there's no such key."""
        with self._lock:
            keys = self._load_for_write()
            kept = [k for k in keys if k.id != key_id]
            if len(kept) == len(keys):
                raise ValueError(f"no key with id {key_id!r} in {self.path}")
            self._write(kept)

    def _load_for_write(self):
        self._stamp = None
        self._refresh()
        return list(self._keys)

    def _write(self, keys):
        folder = self.path.parent
        folder.mkdir(parents=True, exist_ok=True, mode=const.KEYS_DIR_MODE)
        doc = {"version": const.KEYS_FILE_VERSION, "keys": [k.to_dict() for k in keys]}
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".keys-", suffix=".tmp")
        try:
            os.chmod(tmp, const.KEYS_FILE_MODE)  # mkstemp is 0600 already; keep it explicit
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self._stamp = None
        self._refresh()
