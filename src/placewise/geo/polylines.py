"""Encoded polylines: the compact text form of a path used by Google Maps, OSRM, Valhalla and
others, e.g. "_p~iF~ps|U_ulLnnqC_mqNvxq`@".

Each coordinate is rounded to `precision` decimal places, stored as the change from the previous
point and written as base-64 printable ASCII, 5 bits per character
(https://developers.google.com/maps/documentation/utilities/polylinealgorithm). Precision 5 is
Google's; OSRM and Valhalla use 6, and the text does not say which it is.
"""

import numpy as np

from placewise.constants.polylines import (
    CHAR_OFFSET,
    CHUNK_BITS,
    CHUNK_MASK,
    CONTINUATION_BIT,
    DEFAULT_PRECISION,
)


def polyline_encode(points, precision=DEFAULT_PRECISION):
    """Encoded polyline of a sequence of (lat, lon) pairs or an (n, 2) array."""
    points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if not np.all(np.isfinite(points)):
        raise ValueError("cannot encode non-finite coordinates")
    scaled = np.abs(points) * 10.0**precision
    # round half away from zero, so a path and its mirror image encode symmetrically
    ints = (np.sign(points) * np.floor(scaled + 0.5)).astype(np.int64)
    # deltas from integers already rounded, so errors don't accumulate along the path
    deltas = np.diff(ints, axis=0, prepend=np.zeros((1, 2), dtype=np.int64))
    return "".join(_encode_value(int(v)) for v in deltas.ravel())


def polyline_decode(text, precision=DEFAULT_PRECISION):
    """(n, 2) float array of the (lat, lon) points in an encoded polyline; empty text gives (0, 2)."""
    values, value, shift = [], 0, 0
    for char in text:
        chunk = ord(char) - CHAR_OFFSET
        if not 0 <= chunk <= CHUNK_MASK | CONTINUATION_BIT:
            raise ValueError(f"invalid polyline character {char!r}")
        value |= (chunk & CHUNK_MASK) << shift
        shift += CHUNK_BITS
        if not chunk & CONTINUATION_BIT:
            # the low bit carries the sign; negatives were stored inverted
            values.append(~(value >> 1) if value & 1 else value >> 1)
            value, shift = 0, 0
    if shift or len(values) % 2:
        raise ValueError("truncated polyline")
    deltas = np.array(values, dtype=np.int64).reshape(-1, 2)
    return np.cumsum(deltas, axis=0) / 10.0**precision


def _encode_value(value):
    # left shift makes room for the sign bit; inverting negatives keeps small magnitudes short
    value = ~(value << 1) if value < 0 else value << 1
    chars = []
    while value >= CONTINUATION_BIT:
        chars.append(chr((CONTINUATION_BIT | (value & CHUNK_MASK)) + CHAR_OFFSET))
        value >>= CHUNK_BITS
    chars.append(chr(value + CHAR_OFFSET))
    return "".join(chars)
