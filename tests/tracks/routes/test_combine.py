"""Combining tracks: concat, merge, split, crop and reverse.

Synthetic tracks along the equator near 20°W, in open ocean, so every answer is exact.
"""

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from placewise.tracks import Track, TrackMeta
from placewise.tracks.routes import concat, crop, merge, reverse, split

T0 = 1.7e9  # 2023-11-14
DAY = 86_400


def _line(times, lon0=-20.0, dlon=1e-5, lat=0.0, segments=None, meta=None, **cols):
    times = np.asarray(times, dtype=float)
    n = len(times)
    return Track(T0 + times, np.full(n, lat), lon0 + dlon * np.arange(n), segments, meta, **cols)


# -- concat -------------------------------------------------------------------------------------


def test_concat_orders_by_time_keeps_segments_and_fills_columns():
    a = _line([0, 10, 20, 30], segments=(0, 2), meta=TrackMeta(name="a", device="phone"))
    b = _line(
        [100, 110, 120],
        lon0=-19.0,
        hr=[120.0, 121.0, 122.0],
        meta=TrackMeta(name="b", device="phone", activity="walking"),
    )
    out = concat([b, a])
    assert_array_equal(out.time, T0 + np.array([0, 10, 20, 30, 100, 110, 120.0]))
    assert out.segments == (0, 2, 4)
    assert out.columns == ("time", "lat", "lon", "hr")
    assert np.isnan(out.hr[:4]).all()
    assert_array_equal(out.hr[4:], [120.0, 121.0, 122.0])
    # names disagree: the first given wins; device agrees; activity is only known for one
    assert out.meta == TrackMeta(name="b", activity="walking", device="phone")
    assert concat([a, b]).meta == TrackMeta(name="a", activity="walking", device="phone")  # gap filled
    assert concat([a, b], meta=TrackMeta(name="x")).meta == TrackMeta(name="x")


def test_concat_rejects_overlap_unless_allowed():
    a = _line([0, 10, 20])
    touching = _line([20, 30])  # starts the moment a ends: not an overlap
    assert len(concat([a, touching])) == 5
    overlapping = _line([15, 25])
    with pytest.raises(ValueError, match="overlap"):
        concat([a, overlapping])
    out = concat([a, overlapping], allow_overlap=True)
    assert len(out) == 5 and out.segments == (0, 3)


def test_concat_skips_empty_and_needs_input():
    a = _line([0, 10])
    assert len(concat([_line([]), a])) == 2
    with pytest.raises(ValueError):
        concat([])


# -- merge --------------------------------------------------------------------------------------


def test_merge_keeps_the_more_accurate_source_per_window():
    phone = _line(np.arange(120), accuracy=np.full(120, 10.0), meta=TrackMeta(device="phone"))
    # 2 m north of the phone, same pace, overlapping it for the window [60, 120)
    watch = _line(np.arange(60, 180), lat=2e-5, accuracy=np.full(120, 4.0), meta=TrackMeta(device="watch"))
    out = merge([phone, watch], window_s=60)
    assert_array_equal(out.time, T0 + np.arange(180.0))
    assert_array_equal(out.accuracy, np.r_[np.full(60, 10.0), np.full(120, 4.0)])
    assert out.segments == (0,)


def test_merge_falls_back_to_sampling_density():
    dense = _line(np.arange(120), meta=TrackMeta(device="phone"))
    sparse = _line(np.arange(0, 120, 5), lat=0.01)
    out = merge([sparse, dense], window_s=60)
    assert_array_equal(out.time, T0 + np.arange(120.0))
    assert np.all(out.lat == 0.0)
    # accuracy on only one source can't be compared: density decides
    acc = _line(np.arange(0, 120, 5), lat=0.01, accuracy=np.full(24, 1.0))
    assert np.all(merge([acc, dense], window_s=60).lat == 0.0)
    assert np.all(merge([acc, dense], prefer="density", window_s=60).lat == 0.0)


def test_merge_drops_near_duplicates_from_other_sources():
    a = _line(np.arange(10), accuracy=np.full(10, 8.0))
    near = _line(np.arange(10) + 0.4, lat=1e-5, accuracy=np.full(10, 3.0))  # ~1.1 m away, same second
    out = merge([a, near], window_s=None)
    assert len(out) == 10
    assert_array_equal(out.accuracy, np.full(10, 3.0))  # the better fix of each pair survives
    far = _line(np.arange(10) + 0.4, lat=1e-4)  # ~11 m away: both kept
    assert len(merge([a, far], window_s=None)) == 20
    # a single source at 10 Hz keeps all its fixes, however close
    fast = _line(np.arange(50) / 10, dlon=1e-7)
    assert len(merge([fast], window_s=None)) == 50


def test_merge_starts_segments_at_gaps():
    a = _line([0, 1, 2])
    b = _line([1000, 1001], lon0=-19.9)
    out = merge([a, b], max_gap_s=300)
    assert out.segments == (0, 3) and len(out) == 5


# -- split, crop, reverse -----------------------------------------------------------------------


def test_split_by_segment_gap_and_day():
    t = _line([0, 10, 20, 30, 40, 50], segments=(0, 3))
    assert [len(p) for p in split(t)] == [3, 3]

    g = _line([0, 10, 20, 1000, 1010, 1020, 1030], segments=(0, 2))
    parts = split(g, by="gap", max_gap_s=300)
    assert [len(p) for p in parts] == [3, 4]
    assert parts[0].segments == (0, 2)  # segments inside a piece survive

    midnight = (T0 // DAY + 1) * DAY - T0  # seconds from T0 to the next UTC midnight
    d = _line(midnight + np.array([-7200, -3600, 3600, 7200]))
    assert [len(p) for p in split(d, by="day")] == [2, 2]
    assert [len(p) for p in split(d, by="day", tz_offset_s=-3 * 3600)] == [4]  # still the evening before
    assert [len(p) for p in split(d, by="day", tz_offset_s=5400)] == [1, 3]

    assert split(_line([]), by="day") == []
    with pytest.raises(ValueError, match="by"):
        split(t, by="week")


def test_crop_is_inclusive_and_open_ended():
    t = _line(np.arange(10) * 10, segments=(0, 4))
    assert_array_equal(crop(t, T0 + 15, T0 + 50).time, T0 + np.array([20, 30, 40, 50.0]))
    assert crop(t, T0 + 15, T0 + 50).segments == (0, 2)
    assert len(crop(t, end=T0 + 30)) == 4
    assert len(crop(t, start=T0 + 30)) == 7
    assert len(crop(t)) == 10


def test_reverse_mirrors_times_segments_and_heading():
    t = Track(
        T0 + np.array([0, 10, 30, 60.0]),
        [0.0, 0.001, 0.002, 0.003],
        [-20.0, -20.0, -20.0, -20.0],
        segments=(0, 1),
        heading=[0.0, 0.0, 10.0, 350.0],
    )
    r = reverse(t)
    assert_array_equal(r.time, T0 + np.array([0, 30, 50, 60.0]))
    assert_array_equal(r.lat, [0.003, 0.002, 0.001, 0.0])
    assert r.segments == (0, 3)
    assert_array_equal(r.heading, [170.0, 190.0, 180.0, 180.0])
    rr = reverse(r)
    assert_array_equal(rr.time, t.time)
    assert_array_equal(rr.heading, t.heading)
    assert rr.segments == t.segments
