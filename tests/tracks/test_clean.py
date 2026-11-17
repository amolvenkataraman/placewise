"""Cleaning operations on synthetic tracks in open ocean (around 0°N 20°W), each with an exact answer."""

import math

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.geo.distances import haversine
from placewise.tracks import Track, TrackMeta
from placewise.tracks.clean import (
    drop_invalid,
    filter_accuracy,
    fix_clock_jumps,
    remove_spikes,
    smooth,
    smooth_elevation,
    sort_and_dedupe,
    split_gaps,
    thin,
)

R_M = MEAN_RADIUS_KM * 1000
T0 = 1.7e9  # 2023-11-14
LAT0, LON0 = 0.0, -20.0
META = TrackMeta(name="Synthetic", activity="running", source="test")


def north(n, speed_ms=5.0, dt=1.0, segments=None, **columns):
    """n points heading due north from (0, -20) at a steady speed."""
    t = np.arange(n) * dt
    lat = LAT0 + np.degrees(speed_ms * t / R_M)
    return Track(T0 + t, lat, np.full(n, LON0), segments=segments, meta=META, **columns)


def east_m(metres):
    """Longitude offset of `metres` east at the equator."""
    return math.degrees(metres / R_M)


def path_m(track):
    return float(np.sum(haversine(track.lat[:-1], track.lon[:-1], track.lat[1:], track.lon[1:]))) * 1000


ALL = [
    sort_and_dedupe,
    drop_invalid,
    lambda t: filter_accuracy(t, 20),
    remove_spikes,
    split_gaps,
    fix_clock_jumps,
    smooth,
    smooth_elevation,
    thin,
]


@pytest.mark.parametrize("fn", ALL)
def test_every_function_returns_a_new_track_and_leaves_the_input_alone(fn):
    t = north(30, segments=(0, 15), ele=np.linspace(0, 10, 30), accuracy=np.full(30, 4.0))
    before = {k: getattr(t, k).copy() for k in t.columns}
    result = fn(t)
    assert isinstance(result, Track) and result is not t
    assert result.meta == META
    for k, v in before.items():
        np.testing.assert_array_equal(getattr(t, k), v)
    assert t.segments == (0, 15)


@pytest.mark.parametrize("fn", ALL)
def test_every_function_accepts_an_empty_track(fn):
    empty = Track(np.zeros(0), np.zeros(0), np.zeros(0), meta=META)
    assert len(fn(empty)) == 0


def test_sort_and_dedupe():
    t = north(6, hr=np.arange(6.0))
    order = [3, 0, 1, 1, 5, 2, 4, 3, 0]  # shuffled, with three exact duplicates
    shuffled = Track.from_columns({k: getattr(t, k)[order] for k in t.columns}, meta=META)
    clean = sort_and_dedupe(shuffled)
    np.testing.assert_array_equal(clean.time, t.time)
    np.testing.assert_array_equal(clean.hr, t.hr)  # other columns travel with their rows
    assert clean.segments == (0,) and clean.meta == META


def test_sort_and_dedupe_keeps_same_time_distinct_positions_and_segments():
    t = north(6, segments=(0, 3))
    lat = t.lat.copy()
    lat[2] = lat[1]  # point 2 now duplicates point 1 in position but not in time: kept
    same_time = Track(np.r_[t.time, t.time[4]], np.r_[lat, lat[4] + 1e-4], np.r_[t.lon, t.lon[4]])
    clean = sort_and_dedupe(same_time)
    assert len(clean) == 7  # a different position at the same instant is not a duplicate
    assert sort_and_dedupe(t).segments == (0, 3)


def test_drop_invalid():
    t = north(8)
    lat, lon, time = t.lat.copy(), t.lon.copy(), t.time.copy()
    lat[1], lon[1] = 0.0, 0.0  # null island: a fix that never happened
    time[3] = np.nan
    time[5] = 0.0  # 1970: before any GPS fix
    time[6] = 4.1e9  # 2099: in the future
    dirty = Track(time, lat, lon, meta=META)
    np.testing.assert_array_equal(drop_invalid(dirty).time, t.time[[0, 2, 4, 7]])
    # the plausible range is configurable
    np.testing.assert_array_equal(drop_invalid(dirty, min_time=-1, max_time=5e9).time[[3, 4]], [0.0, 4.1e9])
    # a genuine fix close to (0, 0) stays
    near = Track([T0, T0 + 1], [0.0, 0.0001], [0.0001, 0.0])
    assert len(drop_invalid(near)) == 2


def test_filter_accuracy():
    t = north(5, accuracy=[3.0, 100.0, 5.0, np.nan, 21.0])
    kept = filter_accuracy(t, 20)
    np.testing.assert_array_equal(kept.time, t.time[[0, 2, 3]])  # unknown accuracy is kept
    no_column = north(5)
    assert len(filter_accuracy(no_column, 20)) == 5


def test_remove_spikes_single_spike():
    t = north(20, hr=np.arange(20.0))
    lon = t.lon.copy()
    lon[7] += east_m(500)  # 500 m out and straight back, at 1 Hz
    spiky = Track(t.time, t.lat, lon, hr=t.hr, meta=META)
    clean = remove_spikes(spiky)
    assert len(clean) == 19
    assert 7.0 not in clean.hr
    np.testing.assert_array_equal(clean.lon, LON0)


def test_remove_spikes_iterates_and_respects_segments():
    t = north(40, segments=(0, 20))
    lon = t.lon.copy()
    lon[[5, 6]] += [east_m(400), -east_m(400)]  # a two-point excursion
    lon[25] += east_m(300)
    lon[20] += east_m(300)  # a segment's first point has no left neighbour to agree with: kept
    clean = remove_spikes(Track(t.time, t.lat, lon, segments=t.segments, meta=META))
    assert 25 not in np.searchsorted(t.time, clean.time)
    assert 5 not in np.searchsorted(t.time, clean.time) and 6 not in np.searchsorted(t.time, clean.time)
    assert 20 in np.searchsorted(t.time, clean.time)
    assert clean.segments == (0, 18)


def test_remove_spikes_leaves_genuine_fast_travel_and_jitter():
    plane = north(50, speed_ms=250.0)  # 900 km/h: every leg over the limit, but consistent
    assert len(remove_spikes(plane)) == 50
    t = north(20, speed_ms=1.0)
    lon = t.lon.copy()
    lon[7] += east_m(30)  # under min_jump_m: jitter, not a spike
    assert len(remove_spikes(Track(t.time, t.lat, lon))) == 20
    assert len(remove_spikes(Track(t.time, t.lat, lon), 50, min_jump_m=10)) == 19


def test_split_gaps():
    t = north(10, segments=(0, 2))
    time = t.time.copy()
    time[6:] += 600  # a 10-minute pause before point 6
    gapped = Track(time, t.lat, t.lon, segments=t.segments, meta=META)
    assert split_gaps(gapped).segments == (0, 2, 6)
    assert split_gaps(gapped, max_gap_s=1000).segments == (0, 2)
    lat = t.lat.copy()
    lat[4:] += 0.01  # ~1.1 km jump before point 4
    jumped = Track(t.time, lat, t.lon, meta=META)
    assert split_gaps(jumped).segments == (0,)
    assert split_gaps(jumped, max_jump_m=500).segments == (0, 4)


def test_fix_clock_jumps():
    t = north(20, hr=np.arange(20.0))
    time = t.time.copy()
    time[5] -= 30  # runs backwards
    time[12] += 3 * 86_400  # days ahead of everything else
    time[16] += 50  # a forward blip: the points after it are fine, it is the odd one out
    clean = fix_clock_jumps(Track(time, t.lat, t.lon, hr=t.hr, meta=META))
    np.testing.assert_array_equal(clean.hr, np.delete(np.arange(20.0), [5, 12, 16]))


def test_fix_clock_jumps_keeps_a_multi_day_recording():
    t = north(8 * 24, dt=3600.0)  # hourly fixes for eight days
    assert len(fix_clock_jumps(t)) == len(t)


def circle(n=600, radius_m=300.0, speed_ms=5.0):
    """Points on a circle around (0, -20), one per second, plus their true positions."""
    theta = np.arange(n) * speed_ms / radius_m
    north_m, east_m_ = radius_m * np.sin(theta), radius_m * (1 - np.cos(theta))
    return T0 + np.arange(n, dtype=float), north_m, east_m_


def to_latlon(north_m, east_m_):
    return LAT0 + np.degrees(north_m / R_M), LON0 + np.degrees(east_m_ / R_M)


def error_m(track, north_m, east_m_):
    lat, lon = to_latlon(north_m, east_m_)
    return np.asarray(haversine(track.lat, track.lon, lat, lon)) * 1000


def test_kalman_smoothing_reduces_noise():
    time, n_m, e_m = circle()
    rng = np.random.default_rng(42)
    noisy_n, noisy_e = n_m + rng.normal(0, 5, n_m.size), e_m + rng.normal(0, 5, e_m.size)
    noisy = Track(time, *to_latlon(noisy_n, noisy_e), meta=META, hr=np.full(time.size, 140.0))
    smoothed = smooth(noisy)
    before = np.sqrt(np.mean(error_m(noisy, n_m, e_m) ** 2))
    after = np.sqrt(np.mean(error_m(smoothed, n_m, e_m) ** 2))
    assert after < 0.5 * before  # more than 50 % less RMS error
    np.testing.assert_array_equal(smoothed.time, noisy.time)
    np.testing.assert_array_equal(smoothed.hr, noisy.hr)


def test_kalman_does_not_shift_a_clean_straight_path():
    t = north(300, speed_ms=7.0, segments=(0, 100))
    smoothed = smooth(t)
    shift = np.asarray(haversine(t.lat, t.lon, smoothed.lat, smoothed.lon)) * 1000
    assert shift.max() < 0.01  # under a centimetre
    assert smoothed.segments == (0, 100)


def test_kalman_uses_accuracy():
    t = north(60, accuracy=np.full(60, 3.0))
    lon = t.lon.copy()
    lon[30] += east_m(40)  # one bad fix, 40 m off
    acc = t.accuracy.copy()
    acc[30] = 500.0  # ... that the device knew was bad
    trusting = smooth(Track(t.time, t.lat, lon, accuracy=t.accuracy))
    informed = smooth(Track(t.time, t.lat, lon, accuracy=acc))
    off = lambda s: float(haversine(t.lat[30], LON0, s.lat[30], s.lon[30])) * 1000  # noqa: E731
    assert off(informed) < 1.0 < off(trusting)


def test_smooth_rejects_unknown_method():
    with pytest.raises(ValueError, match="method"):
        smooth(north(5), method="spline")


def test_smooth_elevation_removes_a_spike_and_keeps_a_ramp():
    ele = np.linspace(100, 130, 31)
    spiky = ele.copy()
    spiky[12] += 80  # barometer glitch
    clean = smooth_elevation(north(31, ele=spiky))
    assert np.abs(clean.ele - ele).max() <= 1.0  # replaced by its window's median, one ramp step off
    np.testing.assert_allclose(smooth_elevation(north(31, ele=ele)).ele, ele)  # a clean ramp is untouched


def test_smooth_elevation_works_per_segment_and_keeps_nan():
    ele = np.r_[np.full(10, 100.0), np.full(10, 400.0)]  # a cliff at a segment boundary is not noise
    ele[3] = np.nan
    clean = smooth_elevation(north(20, segments=(0, 10), ele=ele))
    np.testing.assert_array_equal(clean.ele, ele)
    assert smooth_elevation(north(5)).ele is None


def test_smooth_elevation_median_mode():
    ele = np.array([10, 10, 11, 10, 10, 11, 10, 10.0])  # 1 m blips
    flat = smooth_elevation(north(8, ele=ele), window=3, n_sigma=None)  # plain running median
    np.testing.assert_array_equal(flat.ele, 10.0)


def test_thin_by_time_and_distance():
    slow = north(101, speed_ms=1.0)  # 1 m per second: the 10 s rule fires first
    np.testing.assert_array_equal(thin(slow).time - T0, np.arange(0, 101, 10))
    fast = north(31, speed_ms=20.0)  # 20 m per second: 50 m is reached every 3 points
    kept = (thin(fast).time - T0).astype(int)
    np.testing.assert_array_equal(kept, [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30])
    assert len(thin(fast, every_m=None)) == 4  # 0, 10, 20, 30


def test_thin_keeps_each_segments_ends():
    t = north(25, speed_ms=1.0, segments=(0, 13))
    kept = thin(t)
    np.testing.assert_array_equal(kept.time - T0, [0, 10, 12, 13, 23, 24])
    assert kept.segments == (0, 3)
