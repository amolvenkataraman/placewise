"""GPX text values both ways: coordinates and numbers (xsd:decimal) and ISO 8601 times read, and
decimals, integers, times and XML text written."""

import datetime as dt
import math
import re
from functools import lru_cache

import numpy as np

_NAN = math.nan
# xsd:decimal: digits with an optional point, no exponent, no nan/inf
_DECIMAL = re.compile(r"\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*")
_DECIMAL_CHARS = "0123456789.+-"
_TIME = re.compile(
    r"\s*(\d{4})-(\d\d)-(\d\d)[Tt ](\d\d):(\d\d):(\d\d)(\.\d+)?\s*([Zz]|[+-]\d\d(?::?\d\d)?)?\s*"
)
ACTIVITY_COMMENT = re.compile(r"\s*Activity\s*[=:]\s*(.*?)\s*", re.IGNORECASE)
_DATE = re.compile(r"\d{4}-\d\d-\d\d")
_CLOCK = re.compile(r"\d\d:\d\d:\d\d")
_EPOCH = dt.datetime(1970, 1, 1)
_EPOCH_ORDINAL = _EPOCH.toordinal()


def coordinate(text, limit):
    if text is None:
        return None
    if text.strip(_DECIMAL_CHARS):  # anything beyond plain ASCII digits, point and sign
        if not _DECIMAL.fullmatch(text):
            return None
        value = float(text)
    else:  # over these characters float() takes exactly what xsd:decimal does
        try:
            value = float(text)
        except ValueError:
            return None
    return value if -limit <= value <= limit else None


def number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=4096)
def _day_seconds(year, month, day):
    return (dt.date(year, month, day).toordinal() - _EPOCH_ORDINAL) * 86400


@lru_cache(maxsize=4096)
def _date_seconds(date):
    """Unix seconds at the start of a YYYY-MM-DD day, or None."""
    if not _DATE.fullmatch(date):
        return None
    try:
        return _day_seconds(int(date[:4]), int(date[5:7]), int(date[8:10]))
    except ValueError:
        return None


def parse_time(text):
    # fast path for the overwhelmingly common "2024-05-01T12:00:00Z"
    if text is not None and len(text) == 20 and text[19] == "Z" and text[10] == "T":
        day = _date_seconds(text[:10])
        clock = text[11:19]
        if day is not None and _CLOCK.fullmatch(clock):
            return float(day + int(clock[:2]) * 3600 + int(clock[3:5]) * 60 + int(clock[6:]))
    match = _TIME.fullmatch(text) if text else None
    if match is None:
        return _NAN
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    try:
        seconds = _day_seconds(int(year), int(month), int(day))
    except ValueError:  # 2024-13-45 and the like
        return _NAN
    # a leap second (:60) simply rolls into the next minute
    seconds += int(hour) * 3600 + int(minute) * 60 + int(second)
    if zone and zone.upper() != "Z":
        digits = zone[1:].replace(":", "")
        offset = int(digits[:2]) * 3600 + int(digits[2:4] or 0) * 60
        seconds += -offset if zone[0] == "+" else offset
    return seconds + float(fraction) if fraction else float(seconds)


def escape(text, entities=None):
    """xml.sax.saxutils.escape, without importing xml.sax (which pulls in urllib, http and ssl)."""
    text = text.replace("&", "&amp;").replace(">", "&gt;").replace("<", "&lt;")
    for key, value in (entities or {}).items():
        text = text.replace(key, value)
    return text


def attribute(text):
    return f'"{escape(text, {chr(34): "&quot;"})}"'


def decimal(value):
    # repr is the shortest string that reads back to the same float; xsd:decimal forbids its exponent form
    text = repr(value)
    if "e" in text:
        text = np.format_float_positional(value, trim="-")
    return text[:-2] if text.endswith(".0") else text


def integer(value):
    return str(round(value))


def format_time(value):
    whole = math.floor(value)
    micro = round((value - whole) * 1e6)
    if micro == 1_000_000:
        whole, micro = whole + 1, 0
    stamp = (_EPOCH + dt.timedelta(seconds=whole)).isoformat()
    if micro:
        stamp += f".{micro:06d}".rstrip("0")
    return stamp + "Z"
