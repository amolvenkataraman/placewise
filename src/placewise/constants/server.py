"""The HTTP server, local service and client: limits, keys, rate limits and the cache."""

API_VERSION = "v1"
API_PREFIX = "/v1"

# -- requests ---------------------------------------------------------------------------------------
# A full default batch (10,000 points at full float precision) is about 400 KB of JSON.
MAX_BODY_BYTES = 1_048_576
MAX_QUERY_VALUE_CHARS = 64  # one lat, lon or worldview value
REQUEST_TIMEOUT_S = 30  # per socket read, so a slow or idle client can't hold a thread forever
MAX_CONNECTIONS = 256  # concurrent connections; more get an immediate 503
SHUTDOWN_GRACE_S = 10  # how long SIGTERM waits for requests already being answered
MAX_LOGGED_PATH_CHARS = 200

# Hosts a loopback-bound server answers to; anything else is a DNS-rebinding attempt.
LOOPBACK_HOST_NAMES = ("localhost", "127.0.0.1", "::1", "[::1]")
# Their presence on a keyless loopback server means a reverse proxy is forwarding public traffic.
PROXY_HEADERS = ("Forwarded", "X-Forwarded-For", "X-Real-IP", "X-Forwarded-Host")

# -- API keys ---------------------------------------------------------------------------------------
KEY_BYTES = 32  # random bytes per key: guessing is hopeless, so a plain SHA-256 is a safe store
KEY_PREFIX = "pw_"  # makes leaked keys easy to recognise and to find with secret scanners
KEY_ID_BYTES = 4  # public id, shown by `keys list` and used by `keys revoke`
MAX_KEY_CHARS = 128  # longer Authorization values are rejected before hashing
KEYS_FILE_VERSION = 1
KEYS_FILENAME = "server-keys.json"
ENV_KEYS_FILE = "PLACEWISE_KEYS_FILE"
KEYS_FILE_MODE = 0o600
KEYS_DIR_MODE = 0o700

# -- rate limits (token buckets) --------------------------------------------------------------------
DEFAULT_KEY_RATE_PER_MIN = 600  # per API key; set per key with `keys add --rate-limit`
DEFAULT_IP_RATE_PER_MIN = 1200  # per client address when keys aren't required
BURST_SECONDS = 10  # a bucket holds this many seconds of its rate
POINTS_PER_TOKEN = 100  # a batch costs one token per this many points (at least one)
MAX_BUCKETS = 100_000  # idle (full) buckets are forgotten beyond this

# -- local service ----------------------------------------------------------------------------------
DEFAULT_CACHE_SIZE = 100_000  # results kept in RAM, least recently used dropped first
CACHE_DECIMALS = 5  # coordinates rounded to 1e-5 degrees (about 1 m) for the cache key
SOCKET_MODE = 0o600  # a Unix socket only its owner can connect to

# -- client -----------------------------------------------------------------------------------------
CLIENT_TIMEOUT_S = 30.0
MAX_FIND_TEXT_CHARS = 200  # /v1/find q= and other text values (within=, id=)
MAX_FIND_LIMIT = 50  # results per /v1/find request
DEFAULT_FIND_LIMIT = 10
