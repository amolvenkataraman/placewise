"""Trimming each segment's ends by a fixed distance plus a keyed per-track jitter."""

import numpy as np
import pytest
from privacy_kit import HOME, KEY, OTHER_KEY, T0, along_path_m, same_track, walk

from placewise.privacy.location import trim_ends, trim_jitter_m
from placewise.tracks import Track


def _line(n=401, t0=T0):
    return walk(HOME, [90.0] * (n - 1), step_m=5.0, t0=t0)  # 2 km due east


def _trimmed_m(track, out):
    """Distance removed at the start and at the end of a single-segment track."""
    s = along_path_m(track)
    kept = np.isin(track.time, out.time)
    return s[kept].min(), s[-1] - s[kept].max()


def test_trims_both_ends_by_trim_plus_jitter():
    track = _line()
    out = trim_ends(track, 200.0, 100.0, KEY)
    total = 200.0 + trim_jitter_m(track, 100.0, KEY)
    head, tail = _trimmed_m(track, out)
    assert total <= head < total + 5.0 and total <= tail < total + 5.0  # 5 m = one sample
    assert out.segments == (0,)


def test_jitter_is_per_track_keyed_and_bounded():
    track = _line()
    jitter = trim_jitter_m(track, 100.0, KEY)
    assert 0 <= jitter < 100.0
    assert trim_jitter_m(track, 100.0, KEY) == jitter
    assert trim_jitter_m(track, 100.0, OTHER_KEY) != jitter
    assert trim_jitter_m(_line(t0=T0 + 86400), 100.0, KEY) != jitter  # seeded by the first timestamp
    assert trim_jitter_m(track, 0.0, KEY) == 0.0
    jitters = [trim_jitter_m(_line(t0=T0 + i * 3600), 100.0, KEY) for i in range(100)]
    assert min(jitters) < 20 and max(jitters) > 80


def test_each_segment_is_trimmed_and_short_ones_vanish():
    a = _line()
    b = _line(t0=a.time[-1] + 600)
    short = _line(n=41, t0=b.time[-1] + 600)  # 200 m: shorter than both trims together
    track = Track(
        time=np.r_[a.time, b.time, short.time],
        lat=np.r_[a.lat, b.lat, short.lat],
        lon=np.r_[a.lon, b.lon, short.lon],
        segments=(0, len(a), len(a) + len(b)),
    )
    out = trim_ends(track, 150.0, 50.0, KEY)
    assert len(out.segments) == 2
    total = 150.0 + trim_jitter_m(track, 50.0, KEY)  # one jitter for the whole track
    for original, kept in zip((a, b), out.iter_segments(), strict=True):
        head, tail = _trimmed_m(original, kept)
        assert total <= head < total + 5.0 and total <= tail < total + 5.0


def test_deterministic_and_key_separated():
    track = _line()
    assert same_track(trim_ends(track, 100.0, 200.0, KEY), trim_ends(track, 100.0, 200.0, KEY))
    assert not same_track(trim_ends(track, 100.0, 200.0, KEY), trim_ends(track, 100.0, 200.0, OTHER_KEY))


def test_zero_trim_is_identity_and_bad_input_rejected():
    track = _line()
    assert same_track(trim_ends(track, 0.0, 0.0, KEY), track)
    assert len(trim_ends(Track(time=[], lat=[], lon=[]), 100.0, 10.0, KEY)) == 0
    with pytest.raises(ValueError):
        trim_ends(track, -1.0, 0.0, KEY)
    with pytest.raises(ValueError):
        trim_ends(track, 1.0, -5.0, KEY)
    with pytest.raises(ValueError):
        trim_ends(track, 1.0, 5.0, b"short")
