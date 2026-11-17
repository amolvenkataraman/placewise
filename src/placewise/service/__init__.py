"""The local service: one long-running process that keeps packs memory-mapped and answers cached
in RAM, so other programs on the machine (in any language) get fast answers over HTTP without
loading data themselves. It speaks the same JSON API as the web server (`placewise.server`).

    placewise serve                          # http://127.0.0.1:8770, no keys on loopback
    placewise serve --socket /run/user/1000/placewise.sock

    from placewise.client import Client
    geo = Client("http://127.0.0.1:8770")    # or Client("unix:///run/user/1000/placewise.sock")
    geo.lookup(43.6426, -79.3871)
"""

import logging

from placewise.constants import server as const
from placewise.model import Settings
from placewise.server.app import default_geocoder, is_loopback, make_server, run

from .cache import CachedGeocoder

log = logging.getLogger("placewise.service")


def make_service(
    geocoder=None,
    settings=None,
    *,
    cache_size=const.DEFAULT_CACHE_SIZE,
    host=None,
    port=None,
    socket_path=None,
    keys=None,
    require_keys=None,
    **server_options,
):
    """A bound server with an LRU cache of `cache_size` results in front of the geocoder.

    On loopback or a Unix socket no API keys are needed and there is no per-address rate limit
    (the callers are your own programs); on any other address it is the full web server, with keys.
    Other keyword arguments go to `placewise.server.make_server`."""
    if settings is None:
        settings = getattr(geocoder, "settings", None) or Settings()
    if geocoder is None:
        geocoder = default_geocoder(settings)
    local = socket_path is not None or is_loopback(settings.server.host if host is None else host)
    server_options.setdefault("ip_rate_limit", 0 if local else const.DEFAULT_IP_RATE_PER_MIN)
    return make_server(
        CachedGeocoder(geocoder, cache_size),
        settings,
        keys=keys,
        host=host,
        port=port,
        unix_socket=socket_path,
        require_keys=require_keys,
        **server_options,
    )


def serve(
    geocoder=None,
    settings=None,
    *,
    cache_size=const.DEFAULT_CACHE_SIZE,
    socket_path=None,
    keys_file=None,
    require_keys=None,
    log_to_stderr=True,
    **server_options,
):
    """Build the service and run it until SIGTERM / SIGINT (what `placewise serve` calls)."""
    if log_to_stderr:
        _log_to_stderr()
    server = make_service(
        geocoder,
        settings,
        cache_size=cache_size,
        socket_path=socket_path,
        keys=keys_file,
        require_keys=require_keys,
        **server_options,
    )
    run(server)


def _log_to_stderr():
    root = logging.getLogger("placewise")
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)


__all__ = ["CachedGeocoder", "make_service", "serve"]
