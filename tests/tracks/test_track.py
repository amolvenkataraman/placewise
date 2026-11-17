"""The Track container: columns, validation, segments and slicing. Operations come later."""

import numpy as np
import pytest

from placewise.tracks import Track, TrackMeta


def _track(n=6, **extra):
    return Track(
        time=np.arange(n, dtype=float) * 10 + 1.8e9,
        lat=np.linspace(43.0, 43.01, n),
        lon=np.linspace(-79.0, -79.01, n),
        segments=(0, 3),
        meta=TrackMeta(name="Ride", activity="cycling", source="ride.fit"),
        **extra,
    )


def test_required_and_optional_columns():
    t = _track(hr=np.full(6, 120.0))
    assert len(t) == 6
    assert t.columns == ("time", "lat", "lon", "hr")
    assert t.hr[0] == 120 and t.ele is None
    assert t.meta.activity == "cycling"


def test_validation():
    with pytest.raises(ValueError, match="length"):
        Track(time=np.zeros(3), lat=np.zeros(2), lon=np.zeros(3))
    with pytest.raises(ValueError, match="colour"):
        Track(time=np.zeros(2), lat=np.zeros(2), lon=np.zeros(2), colour=np.zeros(2))
    with pytest.raises(ValueError, match="latitude"):
        Track(time=np.zeros(2), lat=np.array([0, 95.0]), lon=np.zeros(2))
    with pytest.raises(ValueError, match="segment"):
        Track(time=np.zeros(3), lat=np.zeros(3), lon=np.zeros(3), segments=(1,))  # must start at 0
    with pytest.raises(ValueError, match="segment"):
        Track(time=np.zeros(3), lat=np.zeros(3), lon=np.zeros(3), segments=(0, 5))


def test_columns_are_read_only():
    t = _track()
    with pytest.raises(ValueError):
        t.lat[0] = 0


def test_segments_and_mask_slicing():
    t = _track()
    assert [len(s) for s in t.iter_segments()] == [3, 3]
    kept = t[np.array([True, False, True, False, True, True])]  # drops one point from each segment
    assert len(kept) == 4
    assert kept.segments == (0, 2)
    assert [len(s) for s in kept.iter_segments()] == [2, 2]
    assert t[1:5].segments == (0, 2)  # a slice starting mid-segment begins a segment at 0


def test_empty_track_and_from_columns():
    empty = Track(time=np.zeros(0), lat=np.zeros(0), lon=np.zeros(0))
    assert len(empty) == 0 and empty.segments == ()
    t = Track.from_columns({"time": [1.0, 2.0], "lat": [1, 2], "lon": [3, 4], "ele": [100, 101]})
    assert t.ele.dtype == np.float64 and t.segments == (0,)
