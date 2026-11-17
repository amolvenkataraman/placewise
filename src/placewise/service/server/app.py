"""Building and running a server: `make_server` binds a ready server (TCP or Unix socket) with the
right API-key policy for its address, and `run` serves it until SIGTERM / SIGINT with a graceful
stop. The endpoints are in routes.py, the server classes in servers.py."""

import logging
import os
import signal
import socketserver
import threading
import time

from placewise.constants import server as const
from placewise.model import Settings

from . import servers
from .keys import KeyStore
from .security import is_loopback, keys_required

log = logging.getLogger("placewise.server")


def default_geocoder(settings):
    """The real lookup engine, imported only when a server is started without one."""
    from placewise.engine import Geocoder

    return Geocoder(settings=settings)


def make_server(
    geocoder=None,
    settings=None,
    *,
    keys=None,
    host=None,
    port=None,
    unix_socket=None,
    require_keys=None,
    clock=None,
    ip_rate_limit=None,
    max_body=const.MAX_BODY_BYTES,
    max_connections=const.MAX_CONNECTIONS,
):
    """A bound, ready server; call `serve_forever()` (or `run(server)` for signal handling).

    geocoder: anything with lookup / lookup_many / data_version / settings; default the real one.
    settings: a Settings; default the geocoder's. host and port override settings.server (port=0
        picks a free port). unix_socket: serve on this path instead of TCP (POSIX).
    keys: a KeyStore or a path to a keys file (default: the per-user keys file, when keys are needed).
    require_keys: None decides from the bind (keys for any non-loopback address, never for a Unix
        socket); True forces them, e.g. behind a reverse proxy on the same machine.
    clock: monotonic seconds, for rate limits and uptime (tests inject a fake).
    ip_rate_limit: requests per minute per client address when keys aren't required; 0 is unlimited.
    """
    if settings is None:
        settings = getattr(geocoder, "settings", None) or Settings()
    if geocoder is None:
        geocoder = default_geocoder(settings)
    if unix_socket is not None:
        address, local = os.fspath(unix_socket), True
        required = bool(require_keys)
    else:
        host = settings.server.host if host is None else host
        port = settings.server.port if port is None else port
        address, local = (host, port), is_loopback(host)
        required = keys_required(host, settings.server) if require_keys is None else bool(require_keys)
    if isinstance(keys, (str, os.PathLike)):
        keys = KeyStore(keys)
    elif keys is None and required:
        keys = KeyStore()
    if required and not keys.list():
        log.warning(
            "API keys are required but %s holds none; add one with: placewise server keys add", keys.path
        )
    if not required and not local:
        log.warning("serving a non-loopback address without API keys (server.require_keys is off)")
    app = dict(
        keys=keys,
        require_keys=required,
        local_only=local,
        check_host=local and unix_socket is None,
        clock=clock or time.monotonic,
        ip_rate_limit=const.DEFAULT_IP_RATE_PER_MIN if ip_rate_limit is None else ip_rate_limit,
        max_body=max_body,
        max_connections=max_connections,
    )
    if unix_socket is not None:
        if not hasattr(socketserver, "ThreadingUnixStreamServer"):
            raise OSError("Unix sockets aren't available on this platform")
        return servers.PlacewiseUnixServer(address, geocoder=geocoder, settings=settings, **app)
    return servers.PlacewiseHTTPServer(address, geocoder=geocoder, settings=settings, **app)


def run(server, *, grace=const.SHUTDOWN_GRACE_S, install_signals=True):
    """Serve until SIGTERM or SIGINT, then stop accepting, let in-flight requests finish (up to
    `grace` seconds) and close."""
    stopping = threading.Event()

    def _stop(signum, frame):
        if not stopping.is_set():
            stopping.set()
            log.info("shutting down")
            threading.Thread(target=server.shutdown, daemon=True).start()

    previous = {}
    if install_signals and threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, _stop)
    log.info(
        "placewise listening on %s (API keys %s)",
        server.url,
        "required" if server.require_keys else "not required",
    )
    try:
        server.serve_forever()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        server.wait_idle(grace)
        server.server_close()


__all__ = ["default_geocoder", "make_server", "run"]
