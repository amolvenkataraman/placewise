"""placewise's web server, for hosting your own instance: the HTTP JSON API with API keys, rate
limits, CORS and coordinate-free logs. See docs/self-hosting.md.

    from placewise.service import make_server, run
    run(make_server())                    # the real Geocoder, settings.server.host/port

Modules: app (make_server, run), servers (the TCP and Unix socket servers), routes (the endpoints),
http (handler plumbing and responses), security (keys, CORS, Host and proxy checks, rate limits),
validation (request input), keys (the API key file), ratelimit (token buckets).
"""

from .app import make_server, run
from .keys import ApiKey, KeyStore, default_keys_path
from .ratelimit import RateLimiter
from .security import is_loopback, keys_required
from .validation import ApiError

__all__ = [
    "ApiError",
    "ApiKey",
    "KeyStore",
    "RateLimiter",
    "default_keys_path",
    "is_loopback",
    "keys_required",
    "make_server",
    "run",
]
