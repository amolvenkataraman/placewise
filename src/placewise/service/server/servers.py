"""The server classes: the shared app state the handler reads (geocoder, settings, keys, limiter,
health, version and attribution answers), the connection limit and graceful stop, over TCP and over
an owner-only Unix socket."""

import contextlib
import json
import os
import socket
import socketserver
import stat
import threading
from http.server import ThreadingHTTPServer

from placewise import __version__
from placewise.constants import server as const

from .http import JSON
from .ratelimit import RateLimiter
from .routes import Handler

_BUSY_BODY = json.dumps(
    {"error": {"code": "busy", "message": "too many connections; retry shortly"}}
).encode()
_BUSY_RESPONSE = (
    b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n"
    b"Content-Length: " + str(len(_BUSY_BODY)).encode() + b"\r\nRetry-After: 1\r\nCache-Control: no-store\r\n"
    b"X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n" + _BUSY_BODY
)


class _App:
    """What the handler needs from its server; mixed into both the TCP and the Unix socket server."""

    daemon_threads = True
    block_on_close = False
    request_queue_size = 128

    def _setup(
        self,
        geocoder,
        settings,
        *,
        keys,
        require_keys,
        local_only,
        check_host,
        clock,
        ip_rate_limit,
        max_body,
        max_connections,
    ):
        self.geocoder = geocoder
        self.settings = settings
        self.keys = keys
        self.require_keys = require_keys
        self.local_only = local_only
        self.check_host = check_host
        self.clock = clock
        self.started = clock()
        self.limiter = RateLimiter(clock=clock)
        self.ip_rate_limit = ip_rate_limit
        self.max_body = max_body
        self._slots = threading.BoundedSemaphore(max_connections)
        self._inflight = 0
        self._idle = threading.Condition()
        self._attribution = {}

    # connection limit: excess connections get a 503 straight from the accepting thread
    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            _refuse_busy(request)
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def request_started(self):
        with self._idle:
            self._inflight += 1

    def request_finished(self):
        with self._idle:
            self._inflight -= 1
            if not self._inflight:
                self._idle.notify_all()

    def wait_idle(self, timeout):
        """Wait (up to `timeout` s) for requests already being answered to finish."""
        with self._idle:
            return self._idle.wait_for(lambda: not self._inflight, timeout)

    def stop(self, grace=const.SHUTDOWN_GRACE_S):
        """Stop accepting, let in-flight requests finish, close. Call from another thread than
        serve_forever."""
        self.shutdown()
        self.wait_idle(grace)
        self.server_close()

    def worldview_settings(self):
        """The Settings whose worldview applies: a locking one (server's, then the geocoder's), else
        the server's."""
        for source in (self.settings, getattr(self.geocoder, "settings", None)):
            worldview = getattr(source, "worldview", None)
            if worldview is not None and worldview.lock:
                return source
        return self.settings

    def worldview_lock(self):
        """The locking WorldviewSettings (server settings first, then the geocoder's), or None."""
        for source in (self.settings, getattr(self.geocoder, "settings", None)):
            worldview = getattr(source, "worldview", None)
            if worldview is not None and worldview.lock:
                return worldview
        return None

    def health(self):
        out = {
            "status": "ok",
            "data_version": self.geocoder.data_version,
            "uptime_s": round(self.clock() - self.started, 3),
        }
        cache_info = getattr(self.geocoder, "cache_info", None)
        if callable(cache_info):
            out["cache"] = cache_info()
        return out

    def version_info(self):
        worldview = self.worldview_settings().worldview
        return {
            "placewise": __version__,
            "api": const.API_VERSION,
            "data_version": self.geocoder.data_version,
            "max_batch": self.settings.server.max_batch,
            # the lock is described here, once; answers only flag that it applied
            "worldview": {"order": list(worldview.order), "locked": bool(worldview.lock)},
        }

    def attribution(self, fmt, everything=False):
        """(content type, body): the sources of the packs served here, or with `everything` (or a
        geocoder that doesn't say which packs it reads) the whole source registry."""
        key = (fmt, everything)
        if key not in self._attribution:
            from placewise import attribution

            sources = attribution.load_sources()
            only = None if everything else _served_sources(self.geocoder, attribution)
            if fmt == "json":
                chosen = sources if only is None else {i: s for i, s in sources.items() if i in set(only)}
                body = json.dumps({i: s.to_dict() for i, s in chosen.items()}, ensure_ascii=False)
                self._attribution[key] = (JSON, body.encode())
            else:
                subject = None if only is None else "the data packs served here"
                body = attribution.render_markdown(only=only, subject=subject)
                self._attribution[key] = ("text/markdown; charset=utf-8", body.encode())
        return self._attribution[key]


def _served_sources(geocoder, attribution):
    """The registry source ids of the packs `geocoder` reads (wrappers such as CachedGeocoder are
    looked through via `.geocoder`); None if it doesn't expose `packs`. Ids the registry lacks
    (a pack built elsewhere) are left out."""
    while geocoder is not None:
        packs = getattr(geocoder, "packs", None)
        if packs is not None:
            known = attribution.load_sources()
            return [i for i in attribution.pack_sources(packs) if i in known]
        geocoder = getattr(geocoder, "geocoder", None)
    return None


def _refuse_busy(request):
    try:
        request.settimeout(0.1)
        with contextlib.suppress(OSError):
            request.recv(65536)  # take the request off the wire so closing doesn't reset the client
        request.sendall(_BUSY_RESPONSE)
        request.shutdown(socket.SHUT_WR)
        while request.recv(65536):
            pass
    except OSError:
        pass


class PlacewiseHTTPServer(_App, ThreadingHTTPServer):
    """The API over TCP."""

    allow_reuse_port = False  # never let another process bind the same port alongside us

    def __init__(self, address, **app):
        self.address_family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        self._setup(**app)
        ThreadingHTTPServer.__init__(self, address, Handler)

    def server_bind(self):
        # HTTPServer.server_bind does a reverse DNS lookup of the host, which can stall start-up
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    @property
    def url(self):
        host, port = self.server_address[:2]
        return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


if hasattr(socketserver, "ThreadingUnixStreamServer"):

    class PlacewiseUnixServer(_App, socketserver.ThreadingUnixStreamServer):
        """The API over a Unix socket that only its owner can connect to (mode 0600)."""

        def __init__(self, path, **app):
            path = os.fspath(path)
            _clear_stale_socket(path)
            self._setup(**app)
            old = os.umask(0o177)  # no window in which others could connect
            try:
                socketserver.ThreadingUnixStreamServer.__init__(self, path, Handler)
            finally:
                os.umask(old)
            os.chmod(path, const.SOCKET_MODE)
            self._inode = os.stat(path).st_ino

        def server_close(self):
            super().server_close()
            try:
                if os.stat(self.server_address).st_ino == self._inode:
                    os.unlink(self.server_address)
            except OSError:
                pass

        @property
        def url(self):
            return f"unix://{self.server_address}"


def _clear_stale_socket(path):
    """Remove a socket file left by a server that died; refuse a live socket or any other file."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(st.st_mode):
        raise OSError(f"{path} exists and is not a socket; not replacing it")
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.settimeout(1)
        probe.connect(path)
    except (ConnectionRefusedError, FileNotFoundError):
        os.unlink(path)
        return
    finally:
        probe.close()
    raise OSError(f"{path} is in use by another server")
