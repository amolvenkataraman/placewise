"""Interpolating positions on a track: great-circle between bracketing fixes, never across segment
breaks or long gaps; photo geotagging, camera clock offsets and resampling.

Synthetic tracks in open ocean near 0°N 20°W.
"""

import numpy as np
import pytest

from placewise.geo import haversine, midpoint
from placewise.tracks import Track
from placewise.tracks.interpolate import estimate_clock_offset, geotag, position_at, resample

T0 = 1.8e9


def _equator(n=13, step_s=600.0, lon0=-20.95, dlon=0.15, segments=None):
    return Track(
        time=T0 + np.arange(n) * step_s,
        lat=np.zeros(n),
        lon=lon0 + dlon * np.arange(n),
        segments=segments,
    )


def _wander(duration_s=7200, step_s=10, speed_m_s=10.0):
    """East for the first half, then north: a path with no two places alike."""
    n = int(duration_s // step_s) + 1
    t = np.arange(n) * step_s
    deg = speed_m_s * t / 111_195.08
    half = deg[n // 2]
    lon = -20.0 + np.minimum(deg, half)
    lat = np.maximum(deg - half, 0.0)
    return Track(time=T0 + t, lat=lat, lon=lon)


def test_midpoint_in_time_is_the_great_circle_midpoint():
    track = Track(time=[T0, T0 + 100], lat=[10.0, 10.5], lon=[-20.0, -19.2])
    lat, lon, ok = position_at(track, T0 + 50)
    mid_lat, mid_lon = midpoint(10.0, -20.0, 10.5, -19.2)
    assert ok is True
    assert lat == pytest.approx(mid_lat, abs=1e-12)
    assert lon == pytest.approx(mid_lon, abs=1e-12)


def test_vectorised_times_exact_fixes_and_outside_the_track():
    track = _equator()
    times = np.array([T0 - 1, T0, T0 + 300, T0 + 600, T0 + 7200, T0 + 7201])
    lat, lon, ok = position_at(track, times)
    np.testing.assert_array_equal(ok, [False, True, True, True, True, False])
    assert np.isnan(lat[0]) and np.isnan(lon[-1])
    np.testing.assert_allclose(lon[1:5], [-20.95, -20.875, -20.8, -20.95 + 0.15 * 12], atol=1e-12)
    np.testing.assert_allclose(lat[1:5], 0.0, atol=1e-12)


def test_no_interpolation_across_a_long_gap():
    track = Track(time=[T0, T0 + 100, T0 + 100 + 3600], lat=[0.0, 0.0, 0.0], lon=[-20.0, -19.99, -19.0])
    _, _, ok = position_at(track, [T0 + 50, T0 + 2000, T0 + 3700], max_gap_s=1800)
    np.testing.assert_array_equal(ok, [True, False, True])  # the last is exactly on a fix
    _, _, ok = position_at(track, T0 + 2000, max_gap_s=7200)
    assert ok is True


def test_no_interpolation_across_a_segment_boundary():
    track = Track(time=[T0, T0 + 10, T0 + 20, T0 + 30], lat=[0.0] * 4, lon=[-20, -19.999, -19.5, -19.499])
    split = Track.from_columns({"time": track.time, "lat": track.lat, "lon": track.lon}, segments=(0, 2))
    assert position_at(track, T0 + 15)[2] is True
    assert position_at(split, T0 + 15)[2] is False
    assert position_at(split, T0 + 25)[2] is True


def test_geotag_applies_the_clock_offset_and_reports_distance_to_the_nearest_fix():
    track = _equator(n=2, step_s=100, lon0=-20.0, dlon=0.01)
    tags = geotag(track, [T0 + 20 - 30, T0 + 999], clock_offset_s=30)
    lat, lon, _ = position_at(track, [T0 + 20, T0 + 1029])
    np.testing.assert_array_equal(tags.ok, [True, False])
    np.testing.assert_allclose(tags.lat[:1], lat[:1])
    np.testing.assert_allclose(tags.lon[:1], lon[:1])
    assert tags.fix_dt_s[0] == pytest.approx(20)
    assert tags.fix_distance_m[0] == pytest.approx(haversine(0, -20, 0, -19.998) * 1000, rel=1e-9)
    assert np.isnan(tags.fix_distance_m[1])


def test_clock_offset_recovered_from_photos_with_gps():
    track = _wander()
    true_times = T0 + np.linspace(600, 6600, 15)
    lat, lon, _ = position_at(track, true_times)
    camera = true_times - 3725  # camera runs 1 h 2 min 5 s slow
    result = estimate_clock_offset(track, camera, lat, lon)
    assert result.offset_s == 3725
    assert result.quality == 1.0
    assert result.method == "gps"
    assert result.residual_m == pytest.approx(0, abs=1e-6)

    # photos without a position are ignored when some have one
    lat[::2] = np.nan
    assert estimate_clock_offset(track, camera, lat, lon).offset_s == 3725


def test_clock_offset_without_gps_centres_the_photos_in_the_recording():
    track = _wander()
    true_times = T0 + np.linspace(1800, 5400, 9)
    camera = true_times + 5000
    result = estimate_clock_offset(track, camera)
    assert result.method == "coverage"
    assert result.offset_s == pytest.approx(-5000, abs=1)
    assert result.quality > 0.9


def test_clock_offset_quality_is_low_when_nothing_fits():
    track = _wander(duration_s=600)
    result = estimate_clock_offset(track, T0 + 50_000 + np.arange(5) * 1000.0, search_s=(-60, 60))
    assert result.quality == 0.0


def test_resample_by_time_within_segments():
    track = Track(
        time=T0 + np.array([0.0, 100, 200, 1000, 1060]),
        lat=np.zeros(5),
        lon=np.array([-20.0, -19.99, -19.98, -19.5, -19.49]),
        segments=(0, 3),
        ele=np.array([0.0, 10, 20, 100, 160]),
    )
    out = resample(track, every_s=25)
    np.testing.assert_allclose(out.time - T0, [*np.arange(0, 201, 25), 1000, 1025, 1050])
    assert out.segments == (0, 9)
    _, lon, _ = position_at(track, out.time)
    np.testing.assert_allclose(out.lon, lon, atol=1e-12)
    np.testing.assert_allclose(out.ele, [0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 100, 125, 150])


def test_resample_by_distance_spaces_points_evenly():
    lon = -20.0 + np.array([0.0, 0.003, 0.004, 0.02, 0.05, 0.1])
    track = Track(time=T0 + np.arange(6) * 60.0, lat=np.zeros(6), lon=lon)
    out = resample(track, every_m=1000)
    steps = haversine(out.lat[:-1], out.lon[:-1], out.lat[1:], out.lon[1:]) * 1000
    np.testing.assert_allclose(steps, 1000, rtol=1e-9)
    assert len(out) == 12  # 0 .. 11 km of a 11.12 km path
    # time follows distance linearly within each original step
    _, lon_at, _ = position_at(track, out.time)
    np.testing.assert_allclose(out.lon, lon_at, atol=1e-9)


def test_resample_splits_at_gaps_it_will_not_fill():
    track = Track(
        time=T0 + np.array([0.0, 60, 7260, 7320]), lat=np.zeros(4), lon=[-20, -19.99, -19.9, -19.89]
    )
    out = resample(track, every_s=30, max_gap_s=1800)
    assert out.segments == (0, 3)
    np.testing.assert_allclose(out.time - T0, [0, 30, 60, 7260, 7290, 7320])


def test_resample_needs_exactly_one_spacing():
    track = _equator()
    with pytest.raises(ValueError):
        resample(track)
    with pytest.raises(ValueError):
        resample(track, every_s=10, every_m=10)
    with pytest.raises(ValueError):
        resample(track, every_s=0)


def test_unsorted_track_is_rejected():
    track = Track(time=[T0 + 10, T0], lat=[0.0, 0.0], lon=[-20.0, -20.1])
    with pytest.raises(ValueError, match="sort"):
        position_at(track, T0 + 5)
