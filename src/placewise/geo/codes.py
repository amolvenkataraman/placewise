"""Grid codes: geohash, web-map tiles (the z/x/y scheme of OSM and most tile servers) and quadkeys."""

import math

import numpy as np

from placewise.constants.geohash import ALPHABET as _GEOHASH
from placewise.constants.web_mercator import MAX_LAT as MAX_MERCATOR_LAT

_GEOHASH_INDEX = {c: i for i, c in enumerate(_GEOHASH)}


def geohash_encode(lat, lon, precision=10):
    """Geohash of a point (precision 10 is about 1 m); arrays give string arrays."""
    if np.ndim(lat) or np.ndim(lon):
        lats, lons = np.broadcast_arrays(np.asarray(lat, float), np.asarray(lon, float))
        return np.array([_encode(a, b, precision) for a, b in zip(lats.ravel(), lons.ravel(), strict=True)])
    return _encode(float(lat), float(lon), precision)


def geohash_decode(code):
    """(lat, lon, lat_error, lon_error): the cell centre and its half-sizes in degrees."""
    if not code:
        raise ValueError("empty geohash")
    lat_lo, lat_hi, lon_lo, lon_hi = -90.0, 90.0, -180.0, 180.0
    even = True  # bits alternate lon, lat, lon, ...
    for char in code.lower():
        if char not in _GEOHASH_INDEX:
            raise ValueError(f"invalid geohash character {char!r} in {code!r}")
        bits = _GEOHASH_INDEX[char]
        for shift in range(4, -1, -1):
            bit = (bits >> shift) & 1
            if even:
                mid = (lon_lo + lon_hi) / 2
                lon_lo, lon_hi = (mid, lon_hi) if bit else (lon_lo, mid)
            else:
                mid = (lat_lo + lat_hi) / 2
                lat_lo, lat_hi = (mid, lat_hi) if bit else (lat_lo, mid)
            even = not even
    return (lat_lo + lat_hi) / 2, (lon_lo + lon_hi) / 2, (lat_hi - lat_lo) / 2, (lon_hi - lon_lo) / 2


def tile(lat, lon, zoom):
    """(x, y) of the web-map tile containing the point at a zoom level; arrays give int arrays."""
    n = 2**zoom
    lat = np.clip(np.asarray(lat, dtype=np.float64), -MAX_MERCATOR_LAT, MAX_MERCATOR_LAT)
    lon = np.asarray(lon, dtype=np.float64)
    x = np.floor((lon + 180.0) / 360.0 * n)
    y = np.floor((1.0 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2.0 * n)
    x, y = np.clip(x, 0, n - 1).astype(np.int64), np.clip(y, 0, n - 1).astype(np.int64)
    return (int(x), int(y)) if x.ndim == 0 and y.ndim == 0 else (x, y)


def tile_bounds(x, y, zoom):
    """(south, west, north, east) of a web-map tile."""
    n = 2**zoom

    def lat_of(row):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return (lat_of(y + 1), x / n * 360.0 - 180.0, lat_of(y), (x + 1) / n * 360.0 - 180.0)


def quadkey(x, y, zoom):
    """Bing-style quadkey of a tile: one digit per zoom level."""
    digits = []
    for level in range(zoom, 0, -1):
        mask = 1 << (level - 1)
        digits.append(str((1 if x & mask else 0) + (2 if y & mask else 0)))
    return "".join(digits)


def from_quadkey(key):
    """(x, y, zoom) of a quadkey."""
    x = y = 0
    for i, digit in enumerate(key):
        if digit not in "0123":
            raise ValueError(f"invalid quadkey digit {digit!r} in {key!r}")
        mask = 1 << (len(key) - 1 - i)
        x |= mask if digit in "13" else 0
        y |= mask if digit in "23" else 0
    return x, y, len(key)


def _encode(lat, lon, precision):
    lat_lo, lat_hi, lon_lo, lon_hi = -90.0, 90.0, -180.0, 180.0
    chars, bits, value, even = [], 0, 0, True
    while len(chars) < precision:
        if even:
            mid = (lon_lo + lon_hi) / 2
            bit = lon >= mid
            lon_lo, lon_hi = (mid, lon_hi) if bit else (lon_lo, mid)
        else:
            mid = (lat_lo + lat_hi) / 2
            bit = lat >= mid
            lat_lo, lat_hi = (mid, lat_hi) if bit else (lat_lo, mid)
        value = (value << 1) | bit
        bits += 1
        even = not even
        if bits == 5:
            chars.append(_GEOHASH[value])
            bits = value = 0
    return "".join(chars)
