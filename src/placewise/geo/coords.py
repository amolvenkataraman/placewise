"""Reading and writing coordinates: free text, map-site URLs, EXIF rationals and degrees x 1e7 in;
DMS or decimal text out. WGS84 degrees, (lat, lon) order."""

import math
import re

import numpy as np

from ._arrays import as_floats, out, wrap_lon

# map-site URLs, most specific first: a marker or query point beats the viewport centre
_URL_PATTERNS = [
    re.compile(r"[?&](?:q|query|ll|center|daddr)=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)"),
    re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)"),  # Google place pin
    re.compile(r"mlat=(-?\d+(?:\.\d+)?)&mlon=(-?\d+(?:\.\d+)?)"),  # OpenStreetMap marker
    re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)"),  # Google viewport
    re.compile(r"#map=\d+(?:\.\d+)?/(-?\d+(?:\.\d+)?)/(-?\d+(?:\.\d+)?)"),  # OpenStreetMap viewport
]
# numbers, and hemisphere letters standing alone (so the N in "LON" or E in "HELLO" don't count)
_TOKEN = re.compile(r"(?<![A-Z])[NSEW](?![A-Z])|-?\d+(?:\.\d+)?")
_SYMBOLS = str.maketrans({"′": "'", "’": "'", "″": '"', "”": '"', "º": "°"})


def parse(text):
    """(lat, lon) from free text or a map URL: "43.64, -79.39", "43.64°, -79.39°",
    "43°38′33.2″N 79°23′13.4″W", "N 43° 38.55′ W 79° 23.22′", "43.64N 79.39W", Google Maps or
    OpenStreetMap links. Hemisphere letters decide which value is which when present.
    Raises ValueError for anything ambiguous or out of range."""
    if "://" in text or text.startswith("www."):
        return _parse_url(text)
    tokens = _TOKEN.findall(text.translate(_SYMBOLS).upper())
    letters = [t for t in tokens if t in "NSEW"]
    if letters:
        lat, lon = _parse_hemispheres(tokens, letters, text)
    else:
        numbers = [float(t) for t in tokens]
        if len(numbers) not in (2, 4, 6):
            raise ValueError(f"can't read a coordinate pair from {text!r}")
        half = len(numbers) // 2
        lat, lon = _degrees(numbers[:half], text), _degrees(numbers[half:], text)
    validate(lat, lon)
    return lat, lon


def from_e7(lat_e7, lon_e7):
    """Degrees from integer degrees x 1e7 (Google Takeout, Atlas)."""
    lat, lon = as_floats(lat_e7, lon_e7)
    return out(lat / 1e7), out(lon / 1e7)


def from_exif(dms, ref):
    """Degrees from EXIF GPS values: three (numerator, denominator) rationals (or plain numbers)
    for degrees, minutes, seconds, and the "N"/"S"/"E"/"W" reference."""
    d, m, s = (v[0] / v[1] if isinstance(v, tuple | list) else float(v) for v in dms)
    value = d + m / 60 + s / 3600
    return -value if ref.upper() in ("S", "W") else value


def format_dms(lat, lon, decimals=1):
    """'43°38′33.2″N 79°23′13.4″W' for one point, with seconds rounded to `decimals` places."""
    return f"{_dms(lat, 'NS', decimals)} {_dms(lon, 'EW', decimals)}"


def format_decimal(lat, lon, places=6):
    """'43.642566, -79.387057' for one point (6 places is about 0.1 m)."""
    return f"{lat:.{places}f}, {lon:.{places}f}"


def normalize_lon(lon):
    """Longitude wrapped into [-180, 180)."""
    return out(wrap_lon(lon))


def validate(lat, lon):
    """Raise ValueError unless every lat is in [-90, 90] and every lon in [-180, 180], all finite."""
    lat, lon = as_floats(lat, lon)
    if not (np.all(np.isfinite(lat)) and np.all(np.isfinite(lon))):
        raise ValueError("coordinates must be finite")
    if np.any(np.abs(lat) > 90) or np.any(np.abs(lon) > 180):
        raise ValueError("latitude must be within ±90 and longitude within ±180")


def _parse_url(url):
    for pattern in _URL_PATTERNS:
        if m := pattern.search(url):
            lat, lon = float(m.group(1)), float(m.group(2))
            validate(lat, lon)
            return lat, lon
    raise ValueError(f"no coordinates found in URL {url!r}")


def _parse_hemispheres(tokens, letters, text):
    if len(letters) != 2 or {letters[0] in "NS", letters[1] in "NS"} != {True, False}:
        raise ValueError(f"need one N/S and one E/W hemisphere in {text!r}")
    # "N 43 47" (letter first) or "43 47 N" (letter last): cut the tokens into two groups
    groups, current = [], []
    prefix = tokens[0] in "NSEW"
    for t in tokens:
        if t in "NSEW":
            if prefix and current:
                groups.append(current)
                current = []
            current.append(t)
            if not prefix:
                groups.append(current)
                current = []
        else:
            current.append(t)
    if current:
        groups.append(current)
    values = {}
    for group in groups:
        letter = next(t for t in group if t in "NSEW")
        value = _degrees([float(t) for t in group if t not in "NSEW"], text)
        values["lat" if letter in "NS" else "lon"] = -abs(value) if letter in "SW" else abs(value)
    if len(values) != 2:
        raise ValueError(f"can't read a coordinate pair from {text!r}")
    return values["lat"], values["lon"]


def _degrees(parts, text):
    """Decimal degrees from [deg], [deg, min] or [deg, min, sec]; the sign of deg applies to all."""
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"can't read a coordinate from {text!r}")
    deg, *rest = parts
    if rest and (deg != int(deg) or any(not 0 <= x < 60 for x in rest)):
        raise ValueError(f"invalid degrees/minutes/seconds in {text!r}")
    magnitude = abs(deg) + sum(x / 60**i for i, x in enumerate(rest, start=1))
    return math.copysign(magnitude, deg)


def _dms(value, hemispheres, decimals):
    scale = 10**decimals
    units = round(abs(value) * 3600 * scale)  # integer arithmetic so rounding carries into minutes/degrees
    deg, rem = divmod(units, 3600 * scale)
    minutes, rem = divmod(rem, 60 * scale)
    seconds = rem / scale
    hemisphere = hemispheres[0] if value >= 0 else hemispheres[1]
    return f"{deg}°{minutes:02d}′{seconds:0{3 + decimals}.{decimals}f}″{hemisphere}"
