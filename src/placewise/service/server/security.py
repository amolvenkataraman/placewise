"""Who may call the API: which binds need API keys, Host checks against DNS rebinding on loopback,
refusing proxied requests to a keyless loopback server, CORS, bearer-key authentication and rate
limits. The checks are a mixin for the request handler (routes.py)."""

import ipaddress
import math

from placewise.constants import server as const

from .validation import ApiError


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


class SecurityChecks:
    """Request checks for a handler whose server is the app in servers.py; each raises ApiError."""

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
