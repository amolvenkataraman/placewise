"""The HTTP JSON API's endpoints, shared by the web server and the local service.

Endpoints (all JSON unless noted):

    GET  /v1/lookup?lat=&lon=&worldview=     one Result
    POST /v1/lookup  {"points": [[lat, lon], ...], "worldview": [...]}   {"results": [Result, ...]}

When the operator locked the worldview, the body also says `"worldview_locked": true`, once (beside
the Result's fields, or beside "results"); /v1/version describes the lock.
    GET  /v1/find?q=&limit=&country=&admin1=&near=lat,lon&radius_km=&bbox=s,w,n,e&within=&kinds=
         &prefix=1&strict=0&worldview=&geometry=1      {"results": [Entity, ...]}
    POST /v1/find  {"q": ..., the same names as JSON values}   (keeps `near` out of URLs)
    GET  /v1/get?id=&worldview=&geometry=1  one Entity (404 not_found for an unknown id)
    GET  /v1/health                          {"status", "data_version", "uptime_s"}
    GET  /v1/attribution[?format=json][&all=1]  the served packs' sources (all=1: every source),
                                             as attribution markdown or registry entries
    GET  /v1/version                         {"placewise", "api", "data_version", "max_batch"}

Errors are `{"error": {"code": ..., "message": ...}}` with the matching HTTP status. Coordinates
reveal where people live and travel, so nothing here logs them (or a request line or query string
that holds them) unless `server.log_coordinates` is on; the access log is method, path, status and
duration.
"""

import math
from urllib.parse import urlsplit

from placewise.config import WorldviewLockedError, effective_worldview
from placewise.constants import server as const

from . import validation
from .http import HandlerBase
from .security import SecurityChecks
from .validation import ApiError, bad, coordinate, no_query_params, query_params

LOOKUP = f"{const.API_PREFIX}/lookup"
FIND = f"{const.API_PREFIX}/find"
GET = f"{const.API_PREFIX}/get"
HEALTH = f"{const.API_PREFIX}/health"
ATTRIBUTION = f"{const.API_PREFIX}/attribution"
VERSION = f"{const.API_PREFIX}/version"
# path -> (methods, needs an API key when keys are required)
ROUTES = {
    LOOKUP: (("GET", "POST"), True),
    FIND: (("GET", "POST"), True),
    GET: (("GET",), True),
    HEALTH: (("GET",), False),
    ATTRIBUTION: (("GET",), False),
    VERSION: (("GET",), False),
}


class Handler(SecurityChecks, HandlerBase):
    """The request handler both servers use: checks, routing and the endpoints."""

    routes = ROUTES

    def _handle(self):
        server = self.server
        parts = urlsplit(self.path)
        self._check_host()
        self._check_proxy()
        self._check_origin()
        route = ROUTES.get(parts.path)
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

        if parts.path == LOOKUP:
            bucket = f"key:{key.id}" if key else f"ip:{self._client_id()}"
            per_minute = key.rate_limit if key else server.ip_rate_limit
            self._rate_limit(bucket, per_minute, 1)
            if self.command == "GET":
                return self._lookup_one(parts.query)
            return self._lookup_many(bucket, per_minute)
        if parts.path in (FIND, GET):
            bucket = f"key:{key.id}" if key else f"ip:{self._client_id()}"
            self._rate_limit(bucket, key.rate_limit if key else server.ip_rate_limit, 1)
            if parts.path == GET:
                return self._get(parts.query)
            return self._find(parts.query if self.command == "GET" else None)
        if parts.path == HEALTH:
            return self._health(parts.query)
        if parts.path == VERSION:
            no_query_params(parts.query)
            return self._write_json(200, server.version_info())
        return self._attribution(parts.query)

    # -- endpoints ---------------------------------------------------------------------------------

    def _lookup_one(self, query):
        params = query_params(query, ("lat", "lon", "worldview"))
        for name in ("lat", "lon"):
            if name not in params:
                raise bad(f"{name} is required, e.g. /v1/lookup?lat=43.6426&lon=-79.3871")
        lat = coordinate("lat", params["lat"], text=True)
        lon = coordinate("lon", params["lon"], text=True)
        worldview, locked = self._worldview(params.get("worldview"))
        if self.server.settings.server.log_coordinates:
            self._coords = f" lat={lat!r} lon={lon!r}"
        result = self.server.geocoder.lookup(lat, lon, worldview=worldview)
        self._write_json(200, _locked(result.to_dict(), locked))

    def _lookup_many(self, bucket, per_minute):
        server = self.server
        doc = self._read_json()
        if not isinstance(doc, dict):
            raise bad('the body must be a JSON object: {"points": [[lat, lon], ...]}')
        if unknown := sorted(set(doc) - {"points", "worldview"}):
            raise bad(f"unknown field(s) {', '.join(unknown)[:100]}; allowed: points, worldview")
        points = doc.get("points")
        if not isinstance(points, list):
            raise bad('"points" must be a list of [lat, lon] pairs')
        max_batch = server.settings.server.max_batch
        if len(points) > max_batch:
            raise ApiError(413, "batch_too_large", f"at most {max_batch} points per request; split the batch")
        lats, lons = [], []
        for i, point in enumerate(points):
            if not isinstance(point, list) or len(point) != 2:
                raise bad(f"points[{i}] must be a [lat, lon] pair")
            lats.append(coordinate("lat", point[0], f"points[{i}]: "))
            lons.append(coordinate("lon", point[1], f"points[{i}]: "))
        worldview, locked = self._worldview(doc.get("worldview"))
        extra = max(1, math.ceil(len(points) / const.POINTS_PER_TOKEN)) - 1
        if extra:
            server.limiter.charge(bucket, per_minute, extra)
        if server.settings.server.log_coordinates and points:
            self._coords = f" points={len(points)} first={lats[0]!r},{lons[0]!r}"
        results = server.geocoder.lookup_many(lats, lons, worldview=worldview) if points else []
        if len(results) != len(points):
            raise RuntimeError("geocoder returned a different number of results")
        self._write_json(200, _locked({"results": [r.to_dict() for r in results]}, locked))

    def _find(self, query):
        if query is None:
            doc = self._read_json()
            if not isinstance(doc, dict):
                raise bad('the body must be a JSON object: {"q": "Lake Tahoe", ...}')
            unknown = sorted(set(doc) - set(FIND_PARAMS))
            if unknown:
                raise bad(f"unknown field(s) {', '.join(unknown)[:100]}; allowed: {', '.join(FIND_PARAMS)}")
            params = {k: v for k, v in doc.items() if v is not None}
        else:
            params = query_params(query, FIND_PARAMS)
        if not isinstance(params.get("q"), str) or not params["q"].strip():
            raise bad("q is required, e.g. /v1/find?q=Lake+Tahoe")
        options = find_options(params)
        worldview, locked = self._worldview(params.get("worldview"))
        found = self._search("find", params["q"], worldview=worldview, **options)
        self._write_json(200, _locked({"results": [e.to_dict() for e in found]}, locked))

    def _get(self, query):
        params = query_params(query, ("id", "worldview", "geometry"))
        ident = params.get("id", "")
        if not ident.strip() or len(ident) > const.MAX_FIND_TEXT_CHARS:
            raise bad("id is required, e.g. /v1/get?id=iso:CA-ON")
        worldview, locked = self._worldview(params.get("worldview"))
        geometry = _flag("geometry", params.get("geometry", "0"))
        try:
            entity = self._search("get", ident, worldview=worldview, geometry=geometry)
        except KeyError:
            raise ApiError(404, "not_found", "no place with that id in the served packs") from None
        self._write_json(200, _locked(entity.to_dict(), locked))

    def _search(self, method, text, **options):
        call = getattr(self.server.geocoder, method, None)
        if call is None:
            raise ApiError(501, "not_implemented", "this server's engine has no forward search")
        try:
            return call(text, **options)
        except KeyError:
            raise
        except ValueError as e:
            raise bad(str(e)[:200]) from None

    def _worldview(self, requested):
        """(worldview to pass on, whether the operator's lock applies), decided by
        config.effective_worldview so the server and the lookup engine agree. Locked requests pass
        None and the engine applies its own locked order."""
        requested = validation.worldview(requested)
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

    def _health(self, query):
        no_query_params(query)
        self._write_json(200, self.server.health())

    def _attribution(self, query):
        params = query_params(query, ("format", "all"))
        fmt = params.get("format", "markdown")
        if fmt not in ("markdown", "json"):
            raise bad("format must be markdown or json")
        everything = params.get("all", "0")
        if everything not in ("0", "1"):
            raise bad("all must be 0 or 1")
        content_type, body = self.server.attribution(fmt, everything=everything == "1")
        self._write(200, body, content_type, cache="public, max-age=3600")


FIND_PARAMS = (
    "q", "limit", "country", "admin1", "state", "near", "radius_km", "bbox", "within", "kinds", "prefix",
    "strict", "worldview", "geometry",
)  # fmt: skip


def find_options(params):
    """/v1/find parameters (query-string text or JSON values) as Search.find keyword arguments."""
    for name, value in params.items():
        if isinstance(value, str) and len(value) > const.MAX_FIND_TEXT_CHARS:
            raise bad(f"{name} is too long")
    out = {}
    limit = params.get("limit", const.DEFAULT_FIND_LIMIT)
    try:
        out["limit"] = int(limit)
    except (TypeError, ValueError):
        raise bad("limit must be a whole number") from None
    if not 1 <= out["limit"] <= const.MAX_FIND_LIMIT:
        raise bad(f"limit must be 1-{const.MAX_FIND_LIMIT}")
    for name in ("country", "admin1", "state", "kinds"):
        if name in params:
            out[name] = _list(name, params[name])
    if "within" in params:
        out["within"] = str(params["within"])
    if "near" in params:
        lat, lon = _numbers("near", params["near"], 2)
        out["near"] = (coordinate("lat", lat), coordinate("lon", lon))
    if "radius_km" in params:
        (out["radius_km"],) = _numbers("radius_km", params["radius_km"], 1)
    if "bbox" in params:
        out["bbox"] = _numbers("bbox", params["bbox"], 4)
    for name, default in (("prefix", False), ("strict", True), ("geometry", False)):
        out[name] = _flag(name, params.get(name, default))
    return out


def _list(name, value):
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise bad(f"{name} must be text or a list of text")


def _numbers(name, value, n):
    if isinstance(value, str):
        value = value.split(",")
    elif isinstance(value, int | float) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list | tuple) or len(value) != n:
        raise bad(f"{name} must be {n} number(s)")
    try:
        numbers = tuple(float(v) for v in value if not isinstance(v, bool))
    except (TypeError, ValueError):
        raise bad(f"{name} must be {n} number(s)") from None
    if len(numbers) != n or not all(math.isfinite(v) for v in numbers):
        raise bad(f"{name} must be {n} finite number(s)")
    return numbers


def _flag(name, value):
    if isinstance(value, bool):
        return value
    if value in ("1", "true"):
        return True
    if value in ("0", "false"):
        return False
    raise bad(f"{name} must be 0 or 1")


def _locked(envelope, locked):
    """The response body, flagged once (not per result) when the operator's lock applied."""
    if locked:
        envelope["worldview_locked"] = True
    return envelope
