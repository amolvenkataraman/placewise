"""Request input parsing and validation: coordinates, worldviews, query strings, Content-Length and
JSON bodies, plus the ApiError every check raises (turned into a JSON error answer by the handler)."""

import json
import math
from urllib.parse import parse_qs

from placewise.constants import server as const
from placewise.model import WorldviewSettings


class ApiError(Exception):
    def __init__(self, status, code, message, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def bad(message):
    return ApiError(400, "bad_request", message)


def coordinate(name, value, where="", *, text=False):
    """A validated lat or lon; `text` accepts a query-string value, JSON must hold a number."""
    limit = 90.0 if name == "lat" else 180.0
    if text and isinstance(value, str):
        if not value.strip() or len(value) > const.MAX_QUERY_VALUE_CHARS:
            raise bad(f"{where}{name} must be a number between -{limit:g} and {limit:g}")
        try:
            value = float(value)
        except ValueError:
            raise bad(f"{where}{name} must be a number between -{limit:g} and {limit:g}") from None
    elif type(value) not in (int, float):  # bool is an int subclass, and not a coordinate
        raise bad(f"{where}{name} must be a number between -{limit:g} and {limit:g}")
    if isinstance(value, int) and abs(value) > limit:
        raise bad(f"{where}{name} must be between -{limit:g} and {limit:g}")
    value = float(value)
    if not math.isfinite(value) or abs(value) > limit:
        raise bad(f"{where}{name} must be a finite number between -{limit:g} and {limit:g}")
    return value


def worldview(value):
    """A request's worldview (comma-separated text or a list of strings) as a validated tuple."""
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) > const.MAX_QUERY_VALUE_CHARS:
            raise bad("worldview is too long")
        parts = [p.strip() for p in value.split(",")] if value.strip() else []
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        parts = value
    else:
        raise bad("worldview must be a list of ISO country codes or de_facto, UN, disputed")
    try:
        return WorldviewSettings(order=tuple(parts)).order
    except ValueError as e:
        raise bad(str(e)) from None


def query_params(query, allowed):
    """The query string as {name: value}, refusing unknown and repeated parameters."""
    try:
        params = parse_qs(query, keep_blank_values=True, max_num_fields=len(allowed) + 1)
    except ValueError:
        raise bad(f"too many query parameters; allowed: {', '.join(allowed)}") from None
    if unknown := sorted(set(params) - set(allowed)):
        raise bad(f"unknown query parameter(s) {', '.join(unknown)[:100]}; allowed: {', '.join(allowed)}")
    if repeated := sorted(k for k, v in params.items() if len(v) > 1):
        raise bad(f"query parameter(s) given more than once: {', '.join(repeated)}")
    return {k: v[0] for k, v in params.items()}


def no_query_params(query):
    query_params(query, ())


def content_length(headers, required=True):
    """The Content-Length header as an int; None (or an error when `required`) if missing or bad."""
    text = headers.get("Content-Length")
    if text is None:
        if required:
            raise ApiError(411, "length_required", "send the body with a Content-Length header")
        return None
    if not text.isdigit() or len(text) > 18:
        if required:
            raise bad("invalid Content-Length")
        return None
    return int(text)


def decode_json(raw):
    """A request body as JSON; NaN and Infinity are refused like any other invalid JSON."""
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise bad("the body is not valid JSON") from None


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")
