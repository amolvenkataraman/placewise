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
DEFAULT_DATA_DIR = ".placewise"  # under the home directory, on every platform, unless configured
PACKS_DIR = "packs"
INDEX_CACHE = "index.json"
OVERRIDES_FILE = "overrides.toml"
LOCK_FILE = ".lock"
TEMP_PREFIX = ".tmp-"  # dot-prefixed so pack listing never mistakes a half-built pack for a real one

# Data modes (DataSettings.mode): how packs beyond the world pack arrive.
MODE_AUTO = "auto"  # fetched when a lookup or search needs them (kinds in data.auto_packs)
MODE_MANUAL = "manual"  # only `placewise data install`; the world pack still installs on first use
MODE_LOCKED = "locked"  # never download anything, not even the index (data.offline = true)
MODES = (MODE_AUTO, MODE_MANUAL, MODE_LOCKED)

# Pack kinds (index.json "kind", docs/pack-format.md): what a pack adds to the answers.
KIND_BASE = "base"  # the world pack: countries, admin1, cities, airports, time zones
KIND_COUNTRY = "country"  # one country in depth: municipality, county, metro area, postal code
KIND_PARKS = "parks"
KIND_WATER = "water"
KIND_NOTABLE = "notable"
KIND_POSTAL = "postal"  # postal areas split out of a country pack (it requires that pack)
KIND_OTHER = "other"
PACK_KINDS = (KIND_BASE, KIND_COUNTRY, KIND_PARKS, KIND_WATER, KIND_NOTABLE, KIND_POSTAL, KIND_OTHER)
AUTO_KINDS = (KIND_COUNTRY, KIND_PARKS, KIND_WATER, KIND_NOTABLE, KIND_POSTAL)  # data.auto_packs choices
COVERS_WORLD = "*"  # a pack's `covers` for world-wide data
# A pack whose index entry and pack.json don't name its kind: the name after "<country>-" or
# "world-" says it ("usa-parks", "usa-parks-local", "world-water", "usa-zip"), else its layers do.
SUFFIX_KINDS = {
    "parks": KIND_PARKS,
    "water": KIND_WATER,
    "notable": KIND_NOTABLE,
    "zip": KIND_POSTAL,
    "postal": KIND_POSTAL,
    "postcodes": KIND_POSTAL,
}
LAYER_KINDS = {
    "parks": KIND_PARKS,  # a prefix: parks_national, parks_state ...
    "park_points": KIND_PARKS,
    "marine": KIND_WATER,
    "lakes": KIND_WATER,
    "reservoirs": KIND_WATER,
    "rivers": KIND_WATER,
    "notable": KIND_NOTABLE,
    "zcta": KIND_POSTAL,
    "postal": KIND_POSTAL,
}
# What a search's kinds= asks of the packs (PlaceKind value -> pack kind): a search for parks in
# Canada fetches can-parks in auto mode even when parks aren't in data.auto_packs.
SEARCH_KIND_PACKS = {
    "admin2": KIND_COUNTRY,
    "locality": KIND_COUNTRY,
    "sublocality": KIND_COUNTRY,
    "borough": KIND_COUNTRY,
    "region": KIND_COUNTRY,
    "postal_code": KIND_POSTAL,
    "park": KIND_PARKS,
    "water": KIND_WATER,
    "university": KIND_NOTABLE,
    "building": KIND_NOTABLE,
    "station": KIND_NOTABLE,
    "landmark": KIND_NOTABLE,
    "beach": KIND_NOTABLE,
    "viewpoint": KIND_NOTABLE,
}
# Auto mode plans from the cached index while it is this fresh, so a lookup only touches the
# network when a pack is actually missing.
INDEX_PLAN_MAX_AGE_S = 7 * 24 * 3600

INDEX_SCHEMA = 1  # index.json layout
PACK_SCHEMA = 2  # pack.json / pack layout this code writes (docs/pack-format.md)
PACK_SCHEMAS = frozenset({1, 2})  # pack schemas this code reads and installs
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
# files hashed at once when checking a pack (hashlib releases the GIL, so threads use more cores)
HASH_THREADS = 8

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
