"""Request-handler plumbing: dispatching each request, writing responses with their standard headers,
JSON error answers, reading or draining bodies, and the coordinate-free access log.

The endpoints themselves live in routes.py, on a subclass of HandlerBase.
"""

import json
import logging
import socket
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from placewise.constants import server as const

from .validation import ApiError, bad, content_length, decode_json

log = logging.getLogger("placewise.server")
access_log = logging.getLogger("placewise.server.access")

JSON = "application/json"
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


class HandlerBase(BaseHTTPRequestHandler):
    """Everything but the endpoints. A subclass sets `routes` (the known paths, logged as they are)
    and implements `_handle`, which answers through `_write` / `_write_json` or raises ApiError."""

    protocol_version = "HTTP/1.1"
    timeout = const.REQUEST_TIMEOUT_S
    routes = ()

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

    def _handle(self):
        raise NotImplementedError

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
                raise bad("HTTP/0.9 is not supported")
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
        if path in self.routes:
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

    def _write(self, status, body=b"", content_type=JSON, headers=None, cache="no-store"):
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
        self._write(status, body, JSON, headers, cache)

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
        length = content_length(self.headers, required=False)
        if length is not None and length <= _MAX_DRAIN_BYTES and "Transfer-Encoding" not in self.headers:
            try:
                self.rfile.read(length)
                return
            except OSError:
                pass
        self.close_connection = True

    def _read_json(self):
        if "Transfer-Encoding" in self.headers:
            raise ApiError(411, "length_required", "chunked bodies aren't accepted; send a Content-Length")
        length = content_length(self.headers)
        if length > self.server.max_body:
            raise ApiError(413, "payload_too_large", f"the body is limited to {self.server.max_body} bytes")
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type != JSON:
            raise ApiError(415, "unsupported_media_type", "send the body as Content-Type: application/json")
        raw = self.rfile.read(length)
        self._body_pending = False
        if len(raw) != length:
            self.close_connection = True
            raise bad("the body ended early")
        return decode_json(raw)
