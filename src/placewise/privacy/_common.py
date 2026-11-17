"""Shared pieces: key checks, keyed pseudo-random numbers, along-path distances and point selection."""

import hashlib
import hmac
import struct

import numpy as np

from placewise.constants.privacy import KEY_MIN_BYTES
from placewise.geo import haversine
from placewise.tracks import Track

_DOMAIN = b"placewise.privacy.v1/"
_TWO_53 = float(2**53)


def check_key(key):
    if not isinstance(key, bytes | bytearray):
        raise TypeError(f"key must be bytes (e.g. os.urandom(32)), got {type(key).__name__}")
    if len(key) < KEY_MIN_BYTES:
        raise ValueError(f"key must be at least {KEY_MIN_BYTES} bytes; use os.urandom(32) and keep it")
    return bytes(key)


def keyed_uniforms(key, purpose, *parts, n=1):
    """n reproducible numbers in [0, 1) from HMAC-SHA256(key, purpose + parts). Each purpose has its
    own domain, so a value leaked by one tool says nothing about another's."""
    message = b"\x00".join([_DOMAIN + purpose.encode(), *(_encode(p) for p in parts)])
    out = []
    counter = 0
    while len(out) < n:
        digest = hmac.new(key, message + struct.pack(">I", counter), hashlib.sha256).digest()
        # 53 bits per number: exactly what a float64 mantissa can hold, so [0, 1) stays uniform
        out += [(int.from_bytes(digest[i : i + 8], "big") >> 11) / _TWO_53 for i in range(0, 32, 8)]
        counter += 1
    return out[:n]


def _encode(part):
    if isinstance(part, bytes):
        return part
    if isinstance(part, str):
        return part.encode()
    if isinstance(part, float):
        return struct.pack(">d", part)
    if isinstance(part, int):
        return part.to_bytes(16, "big", signed=True)
    raise TypeError(f"can't encode {type(part).__name__} for HMAC")


def segment_bounds(track):
    return list(zip(track.segments, (*track.segments[1:], len(track)), strict=True))


def along_path_m(track):
    """Metres travelled from the start of each point's segment."""
    s = np.zeros(len(track))
    for start, end in segment_bounds(track):
        lat, lon = track.lat[start:end], track.lon[start:end]
        steps = np.asarray(haversine(lat[:-1], lon[:-1], lat[1:], lon[1:])) * 1000
        s[start + 1 : end] = np.cumsum(steps)
    return s


def select(track, keep):
    """Keep the masked points; a gap left by removed points inside a segment starts a new segment
    (Track's own mask slicing would join the two sides as if the recording were continuous)."""
    index = np.flatnonzero(keep)
    if len(index) == len(track):
        return track
    segment_of = np.searchsorted(np.asarray(track.segments), np.arange(len(track)), side="right") - 1
    seg = segment_of[index]
    new = np.r_[True, (seg[1:] != seg[:-1]) | (np.diff(index) > 1)] if len(index) else np.zeros(0, bool)
    columns = {c: getattr(track, c)[index] for c in track.columns}
    return Track.from_columns(columns, tuple(int(i) for i in np.flatnonzero(new)), track.meta)


def replace_columns(track, meta=None, drop=(), **columns):
    merged = {c: getattr(track, c) for c in track.columns if c not in drop}
    merged.update(columns)
    return Track.from_columns(merged, track.segments, track.meta if meta is None else meta)
