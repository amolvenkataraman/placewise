"""A client for the placewise HTTP API (a local service or a hosted server), with the same
`lookup` / `lookup_many` / `find` / `get` interface as the library's Geocoder, so switching is one line:

    geo = Geocoder()                                          # in-process
    geo = Client("http://127.0.0.1:8770")                     # the local service
    geo = Client("unix:///run/user/1000/placewise.sock")      # the local service, Unix socket
    geo = Client("https://geo.example.org", key="pw_...")     # a hosted server

Lookups are sent as POST bodies even for one point, so coordinates never appear in URLs (and so in
proxy logs or browser history). Large `lookup_many` calls are split into the server's max_batch.
Uses only the standard library; one keep-alive connection per thread.
"""

import http.client
import json
import math
import socket
import ssl
import threading
import warnings
from urllib.parse import urlsplit

from placewise import __version__
from placewise.constants import defaults
from placewise.constants import server as const
from placewise.model import Entity, Result


class ServiceError(Exception):
    """An error answer from the server. `status` is the HTTP status, `code` the API's error code."""

    def __init__(self, message, *, status=None, code=None):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code

    def __str__(self):
        prefix = f"{self.status} {self.code}: " if self.status else ""
        return prefix + self.message


class BadRequestError(ServiceError, ValueError):
    """400: the coordinates, worldview or body were rejected (a ValueError, as in the library)."""


class AuthenticationError(ServiceError):
    """401: missing, invalid or revoked API key."""


class ForbiddenError(ServiceError):
    """403: not allowed (browser origin, Host header, proxied request, locked worldview)."""


class NotFoundError(ServiceError):
    """404: no such endpoint; is the URL right?"""


class MethodNotAllowedError(ServiceError):
    """405."""


class PayloadTooLargeError(ServiceError):
    """413: the batch or body is over the server's limit."""


class RateLimitError(ServiceError):
    """429: slow down; `retry_after` is the seconds the server asked to wait."""

    def __init__(self, message, *, status=None, code=None, retry_after=None):
        super().__init__(message, status=status, code=code)
        self.retry_after = retry_after


class ServerError(ServiceError):
    """5xx: the server failed or is overloaded."""


class TransportError(ServiceError, ConnectionError):
    """The server couldn't be reached, timed out or didn't answer in the API's format."""


_BY_STATUS = {
    400: BadRequestError,
    401: AuthenticationError,
    403: ForbiddenError,
    404: NotFoundError,
    405: MethodNotAllowedError,
    413: PayloadTooLargeError,
    429: RateLimitError,
}
_RETRYABLE = (
    http.client.RemoteDisconnected,
    http.client.BadStatusLine,
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            sock.connect(self._path)
        except BaseException:
            sock.close()
            raise
        self.sock = sock


class Client:
    """`Client(url, key=None, timeout=30)`; url is http://, https:// or unix:///path/to.sock.

    max_batch: points per request; by default the server's (asked once, from /v1/version).
    headers: extra request headers."""

    def __init__(self, url, key=None, timeout=const.CLIENT_TIMEOUT_S, *, max_batch=None, headers=None):
        parts = urlsplit(url)
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout
        self.max_batch = max_batch
        self._extra_headers = dict(headers or {})
        self._local = threading.local()
        if parts.scheme == "unix":
            if not parts.path:
                raise ValueError("a unix URL names the socket path: unix:///run/user/1000/placewise.sock")
            self._target = ("unix", parts.path)
            self._base = ""
        elif parts.scheme in ("http", "https") and parts.hostname:
            self._target = (parts.scheme, parts.hostname, parts.port)
            self._base = parts.path.rstrip("/")
            if key and parts.scheme == "http" and not _is_loopback_name(parts.hostname):
                warnings.warn(
                    f"sending an API key over plain http to {parts.hostname}; use https", stacklevel=2
                )
        else:
            raise ValueError(f"unsupported URL {url!r}: use http://, https:// or unix:///path")

    def __repr__(self):
        return f"Client({self.url!r})"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        """Close this thread's connection (a later call reconnects)."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -- the Geocoder interface --------------------------------------------------------------------

    def lookup(self, lat, lon, *, worldview=None):
        """One point -> Result."""
        return self._lookup_chunk([float(lat)], [float(lon)], worldview)[0]

    def lookup_many(self, lats, lons, *, worldview=None):
        """Many points -> [Result], in order; split into the server's max_batch transparently."""
        lats, lons = [float(v) for v in lats], [float(v) for v in lons]
        if len(lats) != len(lons):
            raise ValueError(f"lats and lons differ in length ({len(lats)} and {len(lons)})")
        if not lats:
            return []
        size = self._batch_size()
        out = []
        for start in range(0, len(lats), size):
            out += self._lookup_chunk(lats[start : start + size], lons[start : start + size], worldview)
        return out

    def find(self, text, **options):
        """Places named `text` -> [Entity]; the options of placewise.search.find (sent as a POST
        body, so `near` stays out of URLs)."""
        body = {"q": str(text)}
        for name, value in options.items():
            if value is None:
                continue
            if name in ("near", "bbox"):
                value = [value.lat, value.lon] if hasattr(value, "lat") else list(value)
                if hasattr(options[name], "as_tuple"):
                    value = list(options[name].as_tuple())
            elif name in ("country", "admin1", "state", "kinds"):
                value = [value] if isinstance(value, str) else [str(getattr(v, "value", v)) for v in value]
            elif name == "within":
                value = str(getattr(getattr(value, "place", None), "id", value))
            elif name == "worldview" and isinstance(value, str):
                value = [p.strip() for p in value.split(",")]
            body[name] = value
        payload = self._request("POST", "/v1/find", body)
        try:
            return [Entity.from_dict(item) for item in payload["results"]]
        except (KeyError, TypeError, ValueError) as e:
            raise TransportError(f"unexpected answer from {self.url}: {e}") from None

    def get(self, ident, *, worldview=None, geometry=False):
        """The Entity with placewise id `ident`; KeyError when the server doesn't have it."""
        from urllib.parse import urlencode

        query = {"id": str(ident)}
        if worldview is not None:
            query["worldview"] = worldview if isinstance(worldview, str) else ",".join(worldview)
        if geometry:
            query["geometry"] = "1"
        try:
            payload = self._request("GET", "/v1/get?" + urlencode(query))
        except NotFoundError as e:
            if e.code == "not_found" and "id" in e.message:
                raise KeyError(str(ident)) from None
            raise
        try:
            return Entity.from_dict(payload)
        except (TypeError, ValueError) as e:
            raise TransportError(f"unexpected answer from {self.url}: {e}") from None

    def outline(self, ident, simplify_m=None):
        """The place's outline as a GeoJSON geometry dict, as Geocoder.outline (simplified here)."""
        entity = self.get(ident, geometry=True)
        return entity.outline.to_geojson(simplify_m) if entity.outline is not None else None

    @property
    def data_version(self):
        return self.health().get("data_version")

    # -- other endpoints ---------------------------------------------------------------------------

    def health(self):
        return self._request("GET", "/v1/health")

    def version(self):
        return self._request("GET", "/v1/version")

    def attribution(self, format="markdown"):
        """The attribution markdown, or with format="json" the source registry."""
        if format == "json":
            return self._request("GET", "/v1/attribution?format=json")
        return self._request("GET", "/v1/attribution", raw=True)

    # -- plumbing ----------------------------------------------------------------------------------

    def _batch_size(self):
        if self.max_batch is None:
            try:
                self.max_batch = int(self.version().get("max_batch") or defaults.SERVER_MAX_BATCH)
            except (NotFoundError, ValueError, TypeError):
                self.max_batch = defaults.SERVER_MAX_BATCH
        return max(1, int(self.max_batch))

    def _lookup_chunk(self, lats, lons, worldview):
        body = {"points": [[a, b] for a, b in zip(lats, lons, strict=True)]}
        for value in (*lats, *lons):
            if not math.isfinite(value):
                raise BadRequestError("lat and lon must be finite numbers")
        if worldview is not None:
            body["worldview"] = (
                [p.strip() for p in worldview.split(",")] if isinstance(worldview, str) else list(worldview)
            )
        payload = self._request("POST", "/v1/lookup", body)
        try:
            results = [Result.from_dict(item) for item in payload["results"]]
        except (KeyError, TypeError, ValueError) as e:
            raise TransportError(f"unexpected answer from {self.url}: {e}") from None
        if len(results) != len(lats):
            raise TransportError(f"{self.url} answered {len(results)} results for {len(lats)} points")
        return results

    def _connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            if self._target[0] == "unix":
                conn = _UnixConnection(self._target[1], self.timeout)
            elif self._target[0] == "https":
                conn = http.client.HTTPSConnection(
                    self._target[1],
                    self._target[2],
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                )
            else:
                conn = http.client.HTTPConnection(self._target[1], self._target[2], timeout=self.timeout)
            self._local.conn = conn
        return conn

    def _request(self, method, path, body=None, *, raw=False):
        headers = {
            "Accept": "application/json",
            "User-Agent": f"placewise/{__version__}",
            **self._extra_headers,
        }
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        for attempt in (1, 2):
            conn = self._connection()
            reused = conn.sock is not None
            try:
                conn.request(method, self._base + path, body=data, headers=headers)
                resp = conn.getresponse()
                status, reply_headers, content = resp.status, resp.headers, resp.read()
                if resp.will_close:
                    self.close()
                break
            except _RETRYABLE as e:
                self.close()
                if reused and attempt == 1:  # the server dropped an idle keep-alive connection
                    continue
                raise TransportError(f"connection to {self.url} failed: {e}") from None
            except (OSError, http.client.HTTPException) as e:
                self.close()
                raise TransportError(f"can't reach {self.url}: {e}") from None
        if status >= 400:
            raise _error(status, reply_headers, content)
        if raw:
            return content.decode("utf-8")
        try:
            return json.loads(content)
        except ValueError:
            raise TransportError(f"{self.url} didn't answer with JSON (is it a placewise server?)") from None


def _error(status, headers, content):
    try:
        err = json.loads(content)["error"]
        code, message = str(err["code"]), str(err["message"])
    except (ValueError, KeyError, TypeError):
        code, message = "unknown", f"HTTP {status}"
    cls = _BY_STATUS.get(status) or (ServerError if status >= 500 else ServiceError)
    if cls is RateLimitError:
        retry = headers.get("Retry-After")
        return RateLimitError(
            message, status=status, code=code, retry_after=int(retry) if retry and retry.isdigit() else None
        )
    return cls(message, status=status, code=code)


def _is_loopback_name(host):
    import ipaddress

    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


__all__ = [
    "AuthenticationError",
    "BadRequestError",
    "Client",
    "ForbiddenError",
    "MethodNotAllowedError",
    "NotFoundError",
    "PayloadTooLargeError",
    "RateLimitError",
    "ServerError",
    "ServiceError",
    "TransportError",
]
