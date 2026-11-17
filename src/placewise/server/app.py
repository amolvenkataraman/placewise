"""The HTTP JSON API, shared by the web server and the local service.

Endpoints (all JSON unless noted):

    GET  /v1/lookup?lat=&lon=&worldview=     one Result
    POST /v1/lookup  {"points": [[lat, lon], ...], "worldview": [...]}   {"results": [Result, ...]}
    GET  /v1/health                          {"status", "data_version", "uptime_s"}
    GET  /v1/attribution[?format=json]       the attribution markdown, or the source registry
    GET  /v1/version                         {"placewise", "api", "data_version", "max_batch"}

Errors are `{"error": {"code": ..., "message": ...}}` with the matching HTTP status. Coordinates
reveal where people live and travel, so nothing here logs them (or a request line or query string
that holds them) unless `server.log_coordinates` is on; the access log is method, path, status and
duration.
"""

import contextlib
import ipaddress
import json
import logging
import math
import os
import signal
import socket
import socketserver
import stat
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from placewise import __version__
from placewise.config import WorldviewLockedError, effective_worldview
from placewise.constants import server as const
from placewise.model import Settings, WorldviewSettings

from .keys import KeyStore
from .ratelimit import RateLimiter

log = logging.getLogger("placewise.server")
access_log = logging.getLogger("placewise.server.access")

_LOOKUP = f"{const.API_PREFIX}/lookup"
_HEALTH = f"{const.API_PREFIX}/health"
_ATTRIBUTION = f"{const.API_PREFIX}/attribution"
_VERSION = f"{const.API_PREFIX}/version"
# path -> (methods, needs an API key when keys are required)
_ROUTES = {
    _LOOKUP: (("GET", "POST"), True),
    _HEALTH: (("GET",), False),
    _ATTRIBUTION: (("GET",), False),
    _VERSION: (("GET",), False),
}
_JSON = "application/json"
_MAX_DRAIN_BYTES = 4 * const.MAX_BODY_BYTES  # unread bodies up to this are read and dropped, not reset
_STDLIB_ERROR_CODES = {
    400: "bad_request",
    404: "not_found",
    408: "timeout",
    413: "payload_too_large",
    414: "uri_too_long",
    431: "headers_too_large",
    501: "not_implemented",
    505: "http_version_not_supported",
}


class ApiError(Exception):
    def __init__(self, status, code, message, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def _bad(message):
    return ApiError(400, "bad_request", message)


# -- who needs keys ---------------------------------------------------------------------------------


def is_loopback(host):
    """True for localhost and loopback addresses (127.0.0.0/8, ::1); False for "", 0.0.0.0 and names."""
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def keys_required(host, server_settings):
    """API keys are required on any non-loopback bind, unless the operator turned them off."""
    return bool(server_settings.require_keys) and not is_loopback(host)


def default_geocoder(settings):
    """The real lookup engine, imported only when a server is started without one."""
    from placewise.engine import Geocoder

    return Geocoder(settings=settings)


# -- input validation -------------------------------------------------------------------------------


def _coordinate(name, value, where="", *, text=False):
    """A validated lat or lon; `text` accepts a query-string value, JSON must hold a number."""
    limit = 90.0 if name == "lat" else 180.0
    if text and isinstance(value, str):
        if not value.strip() or len(value) > const.MAX_QUERY_VALUE_CHARS:
            raise _bad(f"{where}{name} must be a number between -{limit:g} and {limit:g}")
        try:
            value = float(value)
        except ValueError:
            raise _bad(f"{where}{name} must be a number between -{limit:g} and {limit:g}") from None
    elif type(value) not in (int, float):  # bool is an int subclass, and not a coordinate
        raise _bad(f"{where}{name} must be a number between -{limit:g} and {limit:g}")
    if isinstance(value, int) and abs(value) > limit:
        raise _bad(f"{where}{name} must be between -{limit:g} and {limit:g}")
    value = float(value)
    if not math.isfinite(value) or abs(value) > limit:
        raise _bad(f"{where}{name} must be a finite number between -{limit:g} and {limit:g}")
    return value


def _worldview(value):
    """A request's worldview (comma-separated text or a list of strings) as a validated tuple."""
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) > const.MAX_QUERY_VALUE_CHARS:
            raise _bad("worldview is too long")
        parts = [p.strip() for p in value.split(",")] if value.strip() else []
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        parts = value
    else:
        raise _bad("worldview must be a list of ISO country codes or de_facto, UN, disputed")
    try:
        return WorldviewSettings(order=tuple(parts)).order
    except ValueError as e:
        raise _bad(str(e)) from None


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


# -- request handler --------------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = const.REQUEST_TIMEOUT_S

    def setup(self):
        # TCP only: small keep-alive answers would otherwise wait on delayed ACKs
        self.disable_nagle_algorithm = getattr(self.request, "family", None) != getattr(socket, "AF_UNIX", -1)
        super().setup()

    # The stdlib logs every request line (query string and all) to stderr: silence it entirely.
    def log_message(self, format, *args):
        pass

    def log_request(self, code="-", size="-"):
        pass

    def log_error(self, format, *args):
        pass

    def send_response(self, code, message=None):
        # the stdlib version adds a Server header naming Python and its version; we send none
        self.send_response_only(code, message)
        self.send_header("Date", self.date_time_string())
        self._status = code

    def send_error(self, code, message=None, explain=None):
        """Errors the stdlib raises while parsing (bad request line, unsupported method, long
        headers). The request line may hold coordinates, so it is never echoed or logged."""
        if self.request_version == "HTTP/0.9":  # answer in HTTP/1.x; 0.9 has no status line
            self.request_version = "HTTP/1.0"
        self.close_connection = True
        self._prepare()
        try:
            phrase = HTTPStatus(code).phrase
        except ValueError:
            phrase = "error"
        try:
            self._respond_error(ApiError(int(code), _STDLIB_ERROR_CODES.get(int(code), "error"), phrase))
        finally:
            self._log_access()

    # every method we name goes through one dispatcher, so unknown routes and methods get JSON errors
    def do_GET(self):
        self._dispatch()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_GET  # noqa: N815 - stdlib naming

    # -- plumbing ----------------------------------------------------------------------------------

    def _prepare(self):
        self._started = time.perf_counter()
        self._status = None
        self._cors = {}
        self._coords = ""  # only filled when log_coordinates is on
        self._headers_sent = False
        self._body_pending = self.command not in (None, "GET", "HEAD", "OPTIONS") and bool(
            self.headers
            and (self.headers.get("Content-Length", "0") != "0" or "Transfer-Encoding" in self.headers)
        )

    def _dispatch(self):
        self._prepare()
        server = self.server
        server.request_started()
        try:
            if self.request_version == "HTTP/0.9":
                raise _bad("HTTP/0.9 is not supported")
            self._handle()
        except ApiError as e:
            self._respond_error(e)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as e:  # never leak internals to the client
            if server.settings.server.log_coordinates:
                log.exception("internal error on %s %s", self.command, self._logged_path())
            else:
                log.error("internal error on %s %s: %s", self.command, self._logged_path(), type(e).__name__)
            self._respond_error(ApiError(500, "internal", "internal server error"))
        finally:
            server.request_finished()
            self._log_access()

    def _logged_path(self):
        path = urlsplit(self.path or "").path if self.command else ""
        if path in _ROUTES:
            return path
        if self.server.settings.server.log_coordinates and path:
            return path[: const.MAX_LOGGED_PATH_CHARS]
        return "-"  # unknown paths can carry coordinates too (/lookup/43.6,-79.4)

    def _log_access(self):
        ms = (time.perf_counter() - self._started) * 1000
        access_log.info(
            "%s %s %s %.1fms%s",
            self.command or "-",
            self._logged_path(),
            self._status or "-",
            ms,
            self._coords,
        )

    def _write(self, status, body=b"", content_type=_JSON, headers=None, cache="no-store"):
        if self._headers_sent:
            self.close_connection = True
            return
        self._settle_body()
        self.send_response(status)
        if status != 204:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in {**self._cors, **(headers or {})}.items():
            self.send_header(name, value)
        if self.close_connection:
            self.send_header("Connection", "close")
        self._headers_sent = True
        # headers and body in one write: two small segments would stall on Nagle + delayed ACK
        self._headers_buffer.append(b"\r\n")
        if self.command != "HEAD" and status != 204:
            self._headers_buffer.append(body)
        self.flush_headers()

    def _write_json(self, status, payload, headers=None, cache="no-store"):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        self._write(status, body, _JSON, headers, cache)

    def _respond_error(self, err):
        payload = {"error": {"code": err.code, "message": err.message}}
        try:
            self._write_json(err.status, payload, err.headers)
        except OSError:
            self.close_connection = True

    def _settle_body(self):
        """Before answering without reading the body: read and drop a small one, so the connection
        stays usable and the client isn't reset; otherwise close the connection after answering."""
        if not self._body_pending:
            return
        self._body_pending = False
        length = self._content_length(required=False)
        if length is not None and length <= _MAX_DRAIN_BYTES and "Transfer-Encoding" not in self.headers:
            try:
                self.rfile.read(length)
                return
            except OSError:
                pass
        self.close_connection = True

    def _content_length(self, required=True):
        text = self.headers.get("Content-Length")
        if text is None:
            if required:
                raise ApiError(411, "length_required", "send the body with a Content-Length header")
            return None
        if not text.isdigit() or len(text) > 18:
            if required:
                raise _bad("invalid Content-Length")
            return None
        return int(text)

    # -- request flow ------------------------------------------------------------------------------

    def _handle(self):
        server = self.server
        parts = urlsplit(self.path)
        self._check_host()
        self._check_proxy()
        self._check_origin()
        route = _ROUTES.get(parts.path)
        if route is None:
            raise ApiError(404, "not_found", "no such endpoint; the API is under /v1/")
        methods, needs_key = route
        if self.command == "OPTIONS":
            return self._preflight(methods)
        if self.command not in methods:
            raise ApiError(
                405,
                "method_not_allowed",
                f"use {' or '.join(methods)}",
                {"Allow": ", ".join((*methods, "OPTIONS"))},
            )
        key = self._authenticate() if needs_key else None

        if parts.path == _LOOKUP:
            bucket = f"key:{key.id}" if key else f"ip:{self._client_id()}"
            per_minute = key.rate_limit if key else server.ip_rate_limit
            self._rate_limit(bucket, per_minute, 1)
            if self.command == "GET":
                return self._lookup_one(parts.query)
            return self._lookup_many(bucket, per_minute)
        if parts.path == _HEALTH:
            return self._health(parts.query)
        if parts.path == _VERSION:
            self._no_params(parts.query)
            return self._write_json(200, server.version_info())
        return self._attribution(parts.query)

    def _check_host(self):
        if not self.server.check_host:
            return
        host = self.headers.get("Host")
        if host is None:
            return
        host = host.strip().lower()
        name = host[: host.find("]") + 1] if host.startswith("[") else host.rsplit(":", 1)[0]
        if name in const.LOOPBACK_HOST_NAMES or is_loopback(name):
            return
        raise ApiError(403, "forbidden", "this server only answers requests addressed to localhost")

    def _check_proxy(self):
        server = self.server
        if server.require_keys or not server.local_only:
            return
        if any(h in self.headers for h in const.PROXY_HEADERS):
            raise ApiError(
                403,
                "forbidden",
                "this server listens on loopback without API keys, but the request came through a "
                "proxy; restart it with --require-keys (see docs/self-hosting.md)",
            )

    def _check_origin(self):
        allowed = self.server.settings.server.cors_origins
        origin = self.headers.get("Origin")
        if allowed:
            self._cors["Vary"] = "Origin"
        if origin is None:
            return
        if "*" in allowed:
            self._cors["Access-Control-Allow-Origin"] = "*"
        elif origin in allowed:
            self._cors["Access-Control-Allow-Origin"] = origin
        else:
            raise ApiError(403, "forbidden", "this origin is not allowed (server.cors_origins)")
        self._cors["Access-Control-Expose-Headers"] = "Retry-After"

    def _preflight(self, methods):
        headers = {"Allow": ", ".join((*methods, "OPTIONS"))}
        if "Access-Control-Allow-Origin" in self._cors:
            headers.update(
                {
                    "Access-Control-Allow-Methods": ", ".join((*methods, "OPTIONS")),
                    "Access-Control-Allow-Headers": "Authorization, Content-Type",
                    "Access-Control-Max-Age": "600",
                }
            )
        self._write(204, headers=headers)

    def _authenticate(self):
        server = self.server
        if not server.require_keys:
            return None
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            raise ApiError(
                401,
                "unauthorized",
                "an API key is required: send 'Authorization: Bearer <key>'",
                {"WWW-Authenticate": 'Bearer realm="placewise"'},
            )
        key = server.keys.verify(token) if server.keys is not None else None
        if key is None:
            raise ApiError(
                401,
                "unauthorized",
                "invalid or revoked API key",
                {"WWW-Authenticate": 'Bearer realm="placewise", error="invalid_token"'},
            )
        return key

    def _client_id(self):
        address = self.client_address
        return address[0] if isinstance(address, tuple) and address else "unix"

    def _rate_limit(self, bucket, per_minute, cost):
        wait = self.server.limiter.take(bucket, per_minute, cost)
        if wait > 0:
            raise ApiError(
                429,
                "rate_limited",
                "too many requests; retry after the Retry-After seconds",
                {"Retry-After": str(max(1, math.ceil(wait - 1e-9)))},
            )

    def _params(self, query, allowed):
        try:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=len(allowed) + 1)
        except ValueError:
            raise _bad(f"too many query parameters; allowed: {', '.join(allowed)}") from None
        if unknown := sorted(set(params) - set(allowed)):
            raise _bad(
                f"unknown query parameter(s) {', '.join(unknown)[:100]}; allowed: {', '.join(allowed)}"
            )
        if repeated := sorted(k for k, v in params.items() if len(v) > 1):
            raise _bad(f"query parameter(s) given more than once: {', '.join(repeated)}")
        return {k: v[0] for k, v in params.items()}

    def _no_params(self, query):
        self._params(query, ())

    # -- endpoints ---------------------------------------------------------------------------------

    def _lookup_one(self, query):
        params = self._params(query, ("lat", "lon", "worldview"))
        for name in ("lat", "lon"):
            if name not in params:
                raise _bad(f"{name} is required, e.g. /v1/lookup?lat=43.6426&lon=-79.3871")
        lat = _coordinate("lat", params["lat"], text=True)
        lon = _coordinate("lon", params["lon"], text=True)
        worldview, locked = self._worldview(params.get("worldview"))
        if self.server.settings.server.log_coordinates:
            self._coords = f" lat={lat!r} lon={lon!r}"
        result = self.server.geocoder.lookup(lat, lon, worldview=worldview)
        self._write_json(200, _result_dict(result, locked))

    def _lookup_many(self, bucket, per_minute):
        server = self.server
        doc = self._read_json()
        if not isinstance(doc, dict):
            raise _bad('the body must be a JSON object: {"points": [[lat, lon], ...]}')
        if unknown := sorted(set(doc) - {"points", "worldview"}):
            raise _bad(f"unknown field(s) {', '.join(unknown)[:100]}; allowed: points, worldview")
        points = doc.get("points")
        if not isinstance(points, list):
            raise _bad('"points" must be a list of [lat, lon] pairs')
        max_batch = server.settings.server.max_batch
        if len(points) > max_batch:
            raise ApiError(413, "batch_too_large", f"at most {max_batch} points per request; split the batch")
        lats, lons = [], []
        for i, point in enumerate(points):
            if not isinstance(point, list) or len(point) != 2:
                raise _bad(f"points[{i}] must be a [lat, lon] pair")
            lats.append(_coordinate("lat", point[0], f"points[{i}]: "))
            lons.append(_coordinate("lon", point[1], f"points[{i}]: "))
        worldview, locked = self._worldview(doc.get("worldview"))
        extra = max(1, math.ceil(len(points) / const.POINTS_PER_TOKEN)) - 1
        if extra:
            server.limiter.charge(bucket, per_minute, extra)
        if server.settings.server.log_coordinates and points:
            self._coords = f" points={len(points)} first={lats[0]!r},{lons[0]!r}"
        results = server.geocoder.lookup_many(lats, lons, worldview=worldview) if points else []
        if len(results) != len(points):
            raise RuntimeError("geocoder returned a different number of results")
        self._write_json(200, {"results": [_result_dict(r, locked) for r in results]})

    def _worldview(self, requested):
        """(worldview to pass on, whether the operator's lock applies), decided by
        config.effective_worldview so the server and the lookup engine agree. Locked requests pass
        None and the engine applies its own locked order."""
        requested = _worldview(requested)
        try:
            order, locked = effective_worldview(self.server.worldview_settings(), requested)
        except WorldviewLockedError:
            lock = self.server.worldview_lock()
            raise ApiError(
                403,
                "worldview_locked",
                f"this server's worldview is fixed to {', '.join(lock.order)}; leave worldview out",
            ) from None
        if locked:
            return None, True
        return (order if requested is not None else None), False

    def _read_json(self):
        if "Transfer-Encoding" in self.headers:
            raise ApiError(411, "length_required", "chunked bodies aren't accepted; send a Content-Length")
        length = self._content_length()
        if length > self.server.max_body:
            raise ApiError(413, "payload_too_large", f"the body is limited to {self.server.max_body} bytes")
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != _JSON:
            raise ApiError(415, "unsupported_media_type", "send the body as Content-Type: application/json")
        raw = self.rfile.read(length)
        self._body_pending = False
        if len(raw) != length:
            self.close_connection = True
            raise _bad("the body ended early")
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            raise _bad("the body is not valid JSON") from None

    def _health(self, query):
        self._no_params(query)
        self._write_json(200, self.server.health())

    def _attribution(self, query):
        fmt = self._params(query, ("format",)).get("format", "markdown")
        if fmt not in ("markdown", "json"):
            raise _bad("format must be markdown or json")
        content_type, body = self.server.attribution(fmt)
        self._write(200, body, content_type, cache="public, max-age=3600")


def _result_dict(result, locked):
    out = result.to_dict()
    if locked:
        out["worldview_locked"] = True
    return out


# -- servers ----------------------------------------------------------------------------------------


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
        return {
            "placewise": __version__,
            "api": const.API_VERSION,
            "data_version": self.geocoder.data_version,
            "max_batch": self.settings.server.max_batch,
        }

    def attribution(self, fmt):
        if fmt not in self._attribution:
            from placewise import attribution

            if fmt == "json":
                sources = {i: s.to_dict() for i, s in attribution.load_sources().items()}
                self._attribution[fmt] = (_JSON, json.dumps(sources, ensure_ascii=False).encode())
            else:
                self._attribution[fmt] = (
                    "text/markdown; charset=utf-8",
                    attribution.render_markdown().encode(),
                )
        return self._attribution[fmt]


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
        ThreadingHTTPServer.__init__(self, address, _Handler)

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
                socketserver.ThreadingUnixStreamServer.__init__(self, path, _Handler)
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
        return PlacewiseUnixServer(address, geocoder=geocoder, settings=settings, **app)
    return PlacewiseHTTPServer(address, geocoder=geocoder, settings=settings, **app)


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


__all__ = ["ApiError", "PlacewiseHTTPServer", "is_loopback", "keys_required", "make_server", "run"]
