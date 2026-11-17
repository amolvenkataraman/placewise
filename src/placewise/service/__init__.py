"""Network access to the engine: the HTTP JSON API server (`service.server`), the cached local
service (`service.local`) and the Python client (`service.client`).

    from placewise.service import make_server, run, serve, Client
    run(make_server())                         # a web server; see docs/self-hosting.md
    serve()                                    # the local service, what `placewise serve` runs
    geo = Client("http://127.0.0.1:8770")      # the same lookup / lookup_many as Geocoder
"""

from .client import (
    AuthenticationError,
    BadRequestError,
    Client,
    ForbiddenError,
    MethodNotAllowedError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ServiceError,
    TransportError,
)
from .local import CachedGeocoder, make_service, serve
from .server import ApiKey, KeyStore, RateLimiter, make_server, run

__all__ = [
    "ApiKey",
    "AuthenticationError",
    "BadRequestError",
    "CachedGeocoder",
    "Client",
    "ForbiddenError",
    "KeyStore",
    "MethodNotAllowedError",
    "NotFoundError",
    "PayloadTooLargeError",
    "RateLimitError",
    "RateLimiter",
    "ServerError",
    "ServiceError",
    "TransportError",
    "make_server",
    "make_service",
    "run",
    "serve",
]
