"""The pack store: where packs come from, where they live on disk, and the limits on fetching them."""

# Hosting is not final (GitHub Releases, Codeberg or self-hosting are all still open). Whatever
# wins, a release is one directory holding index.json and the archives it names relatively, so
# moving it later only changes this line; users can already point elsewhere with
# PLACEWISE_INDEX_URL, data.index_url or data.mirrors.
DEFAULT_INDEX_URL = "https://github.com/amolvenkataraman/placewise-data/releases/latest/download/index.json"
INDEX_FILENAME = "index.json"  # appended to a mirror given as a directory

ENV_DATA_DIR = "PLACEWISE_DATA_DIR"
ENV_INDEX_URL = "PLACEWISE_INDEX_URL"

APP_DIR_NAME = "placewise"
PACKS_DIR = "packs"
INDEX_CACHE = "index.json"
OVERRIDES_FILE = "overrides.toml"
LOCK_FILE = ".lock"
TEMP_PREFIX = ".tmp-"  # dot-prefixed so pack listing never mistakes a half-built pack for a real one

INDEX_SCHEMA = 1  # index.json layout
PACK_SCHEMA = 1  # pack.json / pack layout this code reads (docs/pack-format.md)
PACK_MANIFEST = "pack.json"

# Pack names become directory names, so they are restricted to what's safe on every platform.
PACK_NAME_PATTERN = r"[a-z0-9][a-z0-9-]*"
PACK_VERSION_PATTERN = r"\d{4}\.\d{2}(?:\.\d+)?"  # CalVer YYYY.MM with an optional .N re-release

# Generic on purpose: identifies the software, never the person or machine running it.
USER_AGENT = "placewise/{version}"
URL_SCHEMES = ("https", "http", "file")  # file:// for local builds; archive hashes guard plain http
HTTP_TIMEOUT_S = 30.0  # per socket operation, not the whole download

INDEX_MAX_BYTES = 4 * 1024 * 1024  # an index is a few hundred bytes per pack
# Downloads stop at the index's size plus this slack, so a broken or hostile server can't fill the
# disk before the hash check gets to fail; the hash is the real check, so a little leeway is free.
DOWNLOAD_SLACK_BYTES = 64 * 1024
CHUNK_BYTES = 1024 * 1024

# Decompression-bomb guards: the archive's hash is trusted only as far as the index is, so the
# unpacked size is capped too. Packs are numeric arrays that xz shrinks a few times at most.
MAX_UNPACK_RATIO = 50
MIN_UNPACK_LIMIT_BYTES = 64 * 1024 * 1024  # tiny packs may compress well above the ratio
MAX_ARCHIVE_MEMBERS = 100_000

# Lock: a holder refreshes the lock file's mtime while it works, so a lock untouched for this long
# belongs to a process that died, and the next one may take it over.
LOCK_STALE_S = 300.0
LOCK_HEARTBEAT_S = 10.0
LOCK_WAIT_S = 600.0  # how long to wait for another process's install before giving up
LOCK_POLL_S = 0.05
