"""placewise's web server, for hosting your own instance: the HTTP JSON API with API keys, rate
limits, CORS and coordinate-free logs. See docs/self-hosting.md.

    from placewise.server import make_server, run
    run(make_server())                    # the real Geocoder, settings.server.host/port
"""

from .app import ApiError, is_loopback, keys_required, make_server, run
from .keys import ApiKey, KeyStore, default_keys_path
from .ratelimit import RateLimiter

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
