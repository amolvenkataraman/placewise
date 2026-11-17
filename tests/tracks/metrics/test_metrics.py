"""Measurements on synthetic tracks in open ocean (around 0°N 20°W), each with an exact answer."""

import dataclasses
import math

import numpy as np
import pytest

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.tracks import Track
from placewise.tracks.metrics import TrackStats, best_efforts, grade, hr_zones, pace, splits, stats

R_M = MEAN_RADIUS_KM * 1000
T0 = 1.7e9  # 2023-11-14
LAT0, LON0 = 0.0, -20.0


def along_meridian(distance_m, time_s, segments=None, **columns):
    """Points due north of (0, -20) at the given distances (m) and times (s from T0)."""
    lat = LAT0 + np.degrees(np.asarray(distance_m, dtype=float) / R_M)
    return Track(T0 + np.asarray(time_s, dtype=float), lat, np.full(len(lat), LON0), segments, **columns)


def north(n, speed_ms=5.0, dt=1.0, **columns):
    t = np.arange(n) * dt
    return along_meridian(speed_ms * t, t, **columns)


def test_straight_line_at_known_speed():
    t = north(1001, speed_ms=5.0)
    s = stats(t)
    assert isinstance(s, TrackStats)
    delta_phi = math.radians(t.lat[-1] - t.lat[0])
    assert s.distance_km == pytest.approx(MEAN_RADIUS_KM * delta_phi, rel=1e-12)
    assert s.distance_km == pytest.approx(5.0, rel=1e-9)
    assert s.duration_s == 1000 and s.moving_time_s == 1000 and s.stopped_time_s == 0
    assert s.avg_speed_kmh == pytest.approx(18.0, rel=1e-9)
    assert s.avg_moving_speed_kmh == pytest.approx(18.0, rel=1e-9)
    assert s.max_speed_kmh == pytest.approx(18.0, rel=1e-9)
    assert s.points == 1001 and s.segments == 1
    assert s.distance_3d_km is None and s.elevation_gain_m is None and s.min_ele_m is None
    assert s.avg_hr is None and s.max_hr is None and s.avg_power is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.points = 3


def test_a_stop_counts_as_stopped_time():
    # 300 s at 5 m/s, 120 s standing still, 300 s at 5 m/s
    t = np.arange(721.0)
    d = np.where(t <= 300, 5 * t, np.where(t <= 420, 1500.0, 1500 + 5 * (t - 420)))
    s = stats(along_meridian(d, t))
    assert s.moving_time_s == 600 and s.stopped_time_s == 120 and s.duration_s == 720
    assert s.distance_km == pytest.approx(3.0, rel=1e-9)
    assert s.avg_moving_speed_kmh == pytest.approx(18.0, rel=1e-9)
    assert s.avg_speed_kmh == pytest.approx(3.0 / 720 * 3600, rel=1e-9)
    # a higher threshold makes a slow walk stopped
    walk = north(101, speed_ms=1.0)
    assert stats(walk).moving_time_s == 100
    assert stats(walk, moving_speed_kmh=4.0).moving_time_s == 0


def test_gaps_between_segments_add_neither_distance_nor_moving_time():
    first = np.arange(101.0)
    d = np.r_[5 * first, 50_000 + 5 * first]  # a 49.5 km jump ...
    t = np.r_[first, 3600 + first]  # ... during an hour's gap
    s = stats(along_meridian(d, t, segments=(0, 101)))
    assert s.distance_km == pytest.approx(1.0, rel=1e-9)
    assert s.moving_time_s == 200 and s.stopped_time_s == 0
    assert s.duration_s == 3700  # elapsed time includes the gap
    assert s.avg_speed_kmh == pytest.approx(18.0, rel=1e-9)
    assert s.max_speed_kmh == pytest.approx(18.0, rel=1e-9)
    assert s.segments == 2


def sawtooth():
    """0 -> 100 -> 0 -> 100 m in 10 m steps with flat stretches jittering by 2 m in between."""
    up, down = np.arange(0, 101, 10.0), np.arange(90, -1, -10.0)
    jitter_top, jitter_bottom = np.array([98, 100, 98, 100, 98, 100.0]), np.array([2, 0, 2, 0, 2, 0.0])
    return np.r_[up, jitter_top, down, jitter_bottom, up[1:], jitter_top]


def test_elevation_gain_ignores_noise_below_the_threshold():
    ele = sawtooth()
    s = stats(north(len(ele), ele=ele))
    assert s.elevation_gain_m == 200 and s.elevation_loss_m == 100
    naive_gain = np.sum(np.clip(np.diff(ele), 0, None))
    assert naive_gain == 218  # nine jitter rises of 2 m that never went anywhere
    assert s.min_ele_m == 0 and s.max_ele_m == 100
    assert stats(north(len(ele), ele=ele), elevation_threshold_m=1).elevation_gain_m == 218


def test_elevation_counts_the_whole_climb_not_just_threshold_steps():
    # a gentle 1 m-per-point climb to 12 m and back: hysteresis 5 m still reports 12 / 12
    ele = np.r_[np.arange(0, 13.0), np.arange(11, -1, -1.0)]
    s = stats(north(len(ele), ele=ele))
    assert s.elevation_gain_m == 12 and s.elevation_loss_m == 12
    small = np.array([0, 3, 0, 4, 1.0])  # never 5 m from where it started
    assert stats(north(5, ele=small)).elevation_gain_m == 0


def test_distance_3d_and_physiology():
    n = 101
    t = north(n, speed_ms=4.0, ele=np.arange(n) * 3.0, hr=np.r_[np.full(50, 120.0), np.full(51, 160.0)])
    s = stats(t)
    assert s.distance_3d_km == pytest.approx(s.distance_km * 5 / 4, rel=1e-6)  # 3-4-5 per leg
    assert s.max_hr == 160
    # time-weighted: 120 holds for 49.5 s and 160 for 50.5 s (each sample owns half of each leg)
    assert s.avg_hr == pytest.approx((120 * 49.5 + 160 * 50.5) / 100)
    p = stats(north(11, power=np.r_[np.zeros(5), np.full(6, 300.0)]))
    assert p.avg_power == pytest.approx((300 * 5.5) / 10)  # zeros (coasting) count


def test_max_speed_is_robust_to_one_bad_fix():
    t = north(101, speed_ms=5.0)
    lat = t.lat.copy()
    lat[50] += math.degrees(60 / R_M)  # one fix 60 m ahead: raw legs of 65 and 55 m/s
    s = stats(Track(t.time, lat, t.lon))
    assert s.max_speed_kmh == pytest.approx(18.0, rel=1e-6)
    with_device = Track(t.time, lat, t.lon, speed=np.r_[np.full(100, 5.0), 6.0])
    assert stats(with_device).max_speed_kmh == pytest.approx(6.0 * 3.6)


def test_stats_of_tiny_tracks():
    empty = stats(Track(np.zeros(0), np.zeros(0), np.zeros(0)))
    assert empty.points == 0 and empty.distance_km == 0 and empty.duration_s == 0 and empty.segments == 0
    one = stats(north(1, ele=[5.0]))
    assert one.points == 1 and one.distance_km == 0 and one.max_speed_kmh == 0 and one.elevation_gain_m == 0


def test_splits_on_a_3_5_km_track():
    # 3.5 km at 3.5 m/s, 1 Hz: kilometre marks fall between fixes (every 285.71 s)
    n = 1001
    t = np.arange(n, dtype=float)
    track = along_meridian(3.5 * t, t, ele=0.01 * 3.5 * t, hr=100 + 0.1 * t)
    rows = splits(track)
    assert [r.index for r in rows] == [1, 2, 3, 4]
    np.testing.assert_allclose([r.distance_km for r in rows], [1, 1, 1, 0.5], rtol=1e-9)
    np.testing.assert_allclose([r.end_km for r in rows], [1, 2, 3, 3.5], rtol=1e-9)
    full = 1000 / 3.5
    np.testing.assert_allclose([r.duration_s for r in rows], [full, full, full, full / 2], rtol=1e-9)
    np.testing.assert_allclose([r.pace_s_per_km for r in rows], full, rtol=1e-9)
    np.testing.assert_allclose([r.ele_change_m for r in rows], [10, 10, 10, 5], rtol=1e-9)  # 1 % grade
    mid_times = np.array([0.5, 1.5, 2.5, 3.25]) * full
    np.testing.assert_allclose([r.avg_hr for r in rows], 100 + 0.1 * mid_times, rtol=1e-9)


def test_splits_skip_gaps_and_handle_missing_columns():
    first = np.arange(201.0)
    d = np.r_[5 * first, 30_000 + 5 * first]
    t = np.r_[first, 9000 + first]
    rows = splits(along_meridian(d, t, segments=(0, 201)), every_km=0.5)
    np.testing.assert_allclose([r.distance_km for r in rows], [0.5, 0.5, 0.5, 0.5], rtol=1e-9)
    np.testing.assert_allclose([r.duration_s for r in rows], 100, rtol=1e-9)  # the gap is not in a split
    assert rows[0].avg_hr is None and rows[0].ele_change_m is None
    assert splits(Track(np.zeros(0), np.zeros(0), np.zeros(0))) == ()


def test_best_effort_finds_the_fast_kilometre():
    # 2 km at 6 min/km, 1 km at 4 min/km, 2 km at 6 min/km, a fix every 10 m
    d = np.arange(0, 5001, 10.0)
    pace_s_per_m = np.where((d > 2000) & (d <= 3000), 0.24, 0.36)
    t = np.r_[0, np.cumsum(pace_s_per_m[1:] * 10)]
    efforts = best_efforts(along_meridian(d, t))
    assert set(efforts) == {1, 5, 10}
    best = efforts[1]
    assert best.duration_s == pytest.approx(240, rel=1e-9)
    assert best.pace_s_per_km == pytest.approx(240, rel=1e-9)
    assert best.speed_kmh == pytest.approx(15.0, rel=1e-9)
    assert best.start_time == pytest.approx(T0 + 720, rel=1e-12)
    assert efforts[5].duration_s == pytest.approx(240 + 4 * 360, rel=1e-9)
    assert efforts[10] is None  # longer than the track


def test_best_effort_interpolates_inside_legs_and_respects_segments():
    # fixes every 300 m at constant 5 m/s: the best 1 km still takes exactly 200 s
    d = np.arange(0, 3001, 300.0)
    efforts = best_efforts(along_meridian(d, d / 5), distances_km=(1.0,))
    assert efforts[1.0].duration_s == pytest.approx(200, rel=1e-9)
    # two 600 m segments do not combine into a 1 km effort
    seg = np.arange(0, 601, 100.0)
    track = along_meridian(np.r_[seg, 5000 + seg], np.r_[seg / 5, 1000 + seg / 5], segments=(0, 7))
    assert best_efforts(track, distances_km=(1.0,))[1.0] is None


def test_pace():
    assert pace(12.0) == 300.0 and isinstance(pace(12.0), float)
    np.testing.assert_allclose(pace(np.array([10.0, 20.0])), [360.0, 180.0])
    assert pace(0.0) == math.inf


def test_grade():
    d = np.arange(0, 1001, 10.0)
    slope = along_meridian(d, d / 3, ele=0.05 * d)
    np.testing.assert_allclose(grade(slope), 5.0, rtol=1e-9)
    flat = along_meridian(d, d / 3, ele=np.full(d.size, 42.0))
    np.testing.assert_allclose(grade(flat), 0.0, atol=1e-12)
    # a 10 m bump on one fix: at most 10 m over the 100 m window, but 10 m over 20 m in a short one
    bumpy = along_meridian(d, d / 3, ele=np.where(d == 500, 52.0, 42.0))
    assert np.abs(grade(bumpy)).max() == pytest.approx(10.0, rel=1e-6)
    assert np.abs(grade(bumpy, window_m=20)).max() == pytest.approx(50.0, rel=1e-6)
    with pytest.raises(ValueError, match="ele"):
        grade(north(5))


def test_hr_zones():
    t = north(201, hr=np.r_[np.full(100, 130.0), np.full(101, 170.0)])
    zones = hr_zones(t, max_hr=200)
    assert [z.index for z in zones] == [0, 1, 2, 3, 4, 5]
    assert [z.low_bpm for z in zones] == [0, 100, 120, 140, 160, 180]
    assert zones[-1].high_bpm == math.inf
    seconds = [z.seconds for z in zones]
    assert seconds == [0, 0, 99.5, 0, 100.5, 0]
    assert sum(seconds) == stats(t).duration_s
    observed = hr_zones(t)  # max_hr defaults to the track's own maximum, 170
    assert observed[-1].low_bpm == pytest.approx(153.0) and observed[-1].seconds == 100.5
    with pytest.raises(ValueError, match="hr"):
        hr_zones(north(5))
