"""Plus codes (Open Location Code): Google's open grid codes such as "8FVC9G8F+6W", and the short
form ("9G8F+6W") that only makes sense next to a nearby place.

Follows the official specification and passes its test data:
https://github.com/google/open-location-code/blob/main/Documentation/Specification/specification.md

Encoding works in integers (degrees times the units of a 15-digit cell) so the result matches the
reference implementations exactly instead of drifting with float division.
"""

import math
from dataclasses import dataclass

import numpy as np

from placewise.constants.plus_codes import (
    ALPHABET,
    BASE,
    DEFAULT_LENGTH,
    GRID_COLUMNS,
    GRID_ROWS,
    LAT_UNITS_PER_DEGREE,
    LON_UNITS_PER_DEGREE,
    MAX_DIGITS,
    MIN_DIGITS,
    MIN_SHORTENABLE_LENGTH,
    PADDING,
    PAIR_DIGITS,
    PAIR_RESOLUTIONS,
    SEPARATOR,
    SEPARATOR_POSITION,
    SHORTEN_SAFETY,
)

_VALUE = {c: i for i, c in enumerate(ALPHABET)}
_GRID_DIGITS = MAX_DIGITS - PAIR_DIGITS


@dataclass(frozen=True)
class CodeArea:
    """The cell a plus code names: its edges and centre in degrees, and its digit count.

    The north and east edges belong to the neighbouring cells, except at the north pole."""

    south: float
    west: float
    north: float
    east: float
    centre_lat: float
    centre_lon: float
    length: int


def encode(lat, lon, length=DEFAULT_LENGTH):
    """Plus code of a point, `length` digits long (2, 4, 6, 8, 10, or any of 11-15; longer is
    treated as 15). Latitude is clipped to [-90, 90] and longitude wrapped; arrays give string arrays."""
    if length < MIN_DIGITS or (length < PAIR_DIGITS and length % 2):
        raise ValueError(f"invalid plus code length {length}: use 2, 4, 6, 8, or 10 and above")
    length = min(length, MAX_DIGITS)
    if np.ndim(lat) or np.ndim(lon):
        lats, lons = np.broadcast_arrays(np.asarray(lat, float), np.asarray(lon, float))
        codes = [_encode(float(a), float(b), length) for a, b in zip(lats.ravel(), lons.ravel(), strict=True)]
        return np.array(codes, dtype=str).reshape(lats.shape)
    return _encode(float(lat), float(lon), length)


def decode(code):
    """The `CodeArea` of a full plus code (case-insensitive; digits past the 15th are ignored)."""
    if not is_full(code):
        raise ValueError(f"not a valid full plus code: {code!r}")
    digits = code.replace(SEPARATOR, "").replace(PADDING, "").upper()[:MAX_DIGITS]
    pair_digits, grid_digits = digits[:PAIR_DIGITS], digits[PAIR_DIGITS:]

    # sum place values in integer units of a 15-digit cell, so the edges are exact until the
    # final division
    lat_units = lon_units = 0
    for i in range(0, len(pair_digits), 2):
        place = BASE ** (PAIR_DIGITS // 2 - 1 - i // 2)
        lat_units += _VALUE[pair_digits[i]] * place
        lon_units += _VALUE[pair_digits[i + 1]] * place
    lat_units *= GRID_ROWS**_GRID_DIGITS
    lon_units *= GRID_COLUMNS**_GRID_DIGITS
    if grid_digits:
        for j, char in enumerate(grid_digits):
            row, col = divmod(_VALUE[char], GRID_COLUMNS)
            lat_units += row * GRID_ROWS ** (_GRID_DIGITS - 1 - j)
            lon_units += col * GRID_COLUMNS ** (_GRID_DIGITS - 1 - j)
        height = GRID_ROWS ** (_GRID_DIGITS - len(grid_digits))
        width = GRID_COLUMNS ** (_GRID_DIGITS - len(grid_digits))
    else:
        place = BASE ** (PAIR_DIGITS // 2 - len(pair_digits) // 2)
        height, width = place * GRID_ROWS**_GRID_DIGITS, place * GRID_COLUMNS**_GRID_DIGITS

    south = lat_units / LAT_UNITS_PER_DEGREE - 90.0
    west = lon_units / LON_UNITS_PER_DEGREE - 180.0
    north = (lat_units + height) / LAT_UNITS_PER_DEGREE - 90.0
    east = (lon_units + width) / LON_UNITS_PER_DEGREE - 180.0
    return CodeArea(south, west, north, east, (south + north) / 2, (west + east) / 2, len(digits))


def is_valid(code):
    """Whether the string is a well-formed plus code, full or short."""
    if not isinstance(code, str) or code.count(SEPARATOR) != 1 or len(code) < 2:
        return False
    sep = code.index(SEPARATOR)
    if sep > SEPARATOR_POSITION or sep % 2:
        return False
    if any(c != PADDING and c != SEPARATOR and c.upper() not in _VALUE for c in code):
        return False
    pad = code.find(PADDING)
    if pad != -1:
        # padding only fills out a full code shorter than 8 digits: an even run right up to the
        # separator, with nothing after it
        if sep < SEPARATOR_POSITION or pad == 0 or not code.endswith(SEPARATOR):
            return False
        run = code[pad:sep]
        if len(run) % 2 or run.strip(PADDING):
            return False
    # a single digit after the separator would be a half pair
    return len(code) - sep - 1 != 1


def is_short(code):
    """Whether the string is a valid short code (leading digits dropped; needs a reference place)."""
    return is_valid(code) and code.index(SEPARATOR) < SEPARATOR_POSITION


def is_full(code):
    """Whether the string is a valid full code that names a real place on the globe."""
    if not is_valid(code) or is_short(code):
        return False
    # the first pair alone could reach 180 deg latitude or 360 deg longitude past the origin
    return _VALUE[code[0].upper()] * BASE < 180 and _VALUE[code[1].upper()] * BASE < 360


def shorten(code, ref_lat, ref_lon):
    """The shortest form of a full code that still recovers to it from near (ref_lat, ref_lon):
    4, 6 or 8 leading digits dropped, or the code unchanged if the reference is too far away."""
    if not is_full(code):
        raise ValueError(f"not a valid full plus code: {code!r}")
    if PADDING in code:
        raise ValueError(f"padded plus codes cannot be shortened: {code!r}")
    code = code.upper()
    area = decode(code)
    if area.length < MIN_SHORTENABLE_LENGTH:
        raise ValueError(f"plus codes shorter than {MIN_SHORTENABLE_LENGTH} digits cannot be shortened")
    ref_lat, ref_lon = _clip_lat(ref_lat), _normalize_lon(ref_lon)
    offset = max(abs(area.centre_lat - ref_lat), abs(area.centre_lon - ref_lon))
    # dropping 2 * (i + 1) digits leaves the reference to imply a cell PAIR_RESOLUTIONS[i] wide
    for i in range(len(PAIR_RESOLUTIONS) - 2, 0, -1):
        if offset < PAIR_RESOLUTIONS[i] * SHORTEN_SAFETY:
            return code[(i + 1) * 2 :]
    return code


def recover_nearest(short_code, ref_lat, ref_lon):
    """The full code nearest (ref_lat, ref_lon) that ends in `short_code`. A full code comes back
    upper-cased and otherwise unchanged."""
    if is_full(short_code):
        return short_code.upper()
    if not is_short(short_code):
        raise ValueError(f"not a valid short plus code: {short_code!r}")
    ref_lat, ref_lon = _clip_lat(ref_lat), _normalize_lon(ref_lon)
    short_code = short_code.upper()
    missing = SEPARATOR_POSITION - short_code.index(SEPARATOR)
    resolution = float(BASE) ** (2 - missing / 2)  # size of the cell the missing digits pick
    area = decode(encode(ref_lat, ref_lon)[:missing] + short_code)
    lat, lon = area.centre_lat, area.centre_lon
    # the reference's own cell may not be the nearest match: step one cell towards the reference
    # when it is more than half a cell away, without leaving the globe
    if ref_lat + resolution / 2 < lat and lat - resolution >= -90:
        lat -= resolution
    elif ref_lat - resolution / 2 > lat and lat + resolution <= 90:
        lat += resolution
    if ref_lon + resolution / 2 < lon:
        lon -= resolution
    elif ref_lon - resolution / 2 > lon:
        lon += resolution
    return encode(lat, lon, area.length)


def _encode(lat, lon, length):
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError(f"cannot encode non-finite coordinates ({lat}, {lon})")
    lat_units, lon_units = _units(lat, lon)

    # build all 15 digits from least significant up, then cut to length
    grid = []
    for _ in range(_GRID_DIGITS):
        grid.append(ALPHABET[(lat_units % GRID_ROWS) * GRID_COLUMNS + lon_units % GRID_COLUMNS])
        lat_units //= GRID_ROWS
        lon_units //= GRID_COLUMNS
    pairs = []
    for _ in range(PAIR_DIGITS // 2):
        pairs.append(ALPHABET[lat_units % BASE] + ALPHABET[lon_units % BASE])
        lat_units //= BASE
        lon_units //= BASE
    digits = ("".join(reversed(pairs)) + "".join(reversed(grid)))[:length]

    if length < SEPARATOR_POSITION:
        return digits + PADDING * (SEPARATOR_POSITION - length) + SEPARATOR
    return digits[:SEPARATOR_POSITION] + SEPARATOR + digits[SEPARATOR_POSITION:]


def _units(lat, lon):
    """(lat, lon) as whole 15-digit cells north of -90 and east of -180, clipped and wrapped.

    Floors the decimal the float stands for (its shortest repr), not the float product: 40.6 *
    2.5e7 comes out as 1014999999.99... in floats, which would drop a 40.6 deg point into the cell
    below. The reference implementations accept a few such misses; this matches all their data."""
    from fractions import Fraction  # exact decimal arithmetic; loaded only when encoding

    lat_units = math.floor(Fraction(repr(float(lat))) * LAT_UNITS_PER_DEGREE) + 90 * LAT_UNITS_PER_DEGREE
    lat_units = min(max(lat_units, 0), 180 * LAT_UNITS_PER_DEGREE - 1)  # 90 itself goes in the top cell
    lon_units = math.floor(Fraction(repr(float(lon))) * LON_UNITS_PER_DEGREE) + 180 * LON_UNITS_PER_DEGREE
    return lat_units, lon_units % (360 * LON_UNITS_PER_DEGREE)


def _clip_lat(lat):
    return min(90.0, max(-90.0, float(lat)))


def _normalize_lon(lon):
    """Longitude in [-180, 180)."""
    return (float(lon) + 180.0) % 360.0 - 180.0
