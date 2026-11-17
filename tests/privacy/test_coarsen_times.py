"""Time coarsening and shifting."""

import numpy as np
import pytest
from privacy_kit import HOME, RIDE_META, T0, same_track, walk

from placewise.privacy.time import coarsen_times, shift_times
from placewise.tracks import Track


def _track():
    base = walk(HOME, [0.0] * 9, t0=T0 + 86400 * 3 + 3600 * 13 + 60 * 47 + 31.25, dt=97.5, meta=RIDE_META)
    return Track.from_columns(
        {**{c: getattr(base, c) for c in base.columns}, "hr": np.arange(10.0)}, (0, 4), base.meta
    )


@pytest.mark.parametrize(("resolution", "step"), [("minute", 60), ("hour", 3600), ("day", 86400)])
def test_floors_to_the_resolution(resolution, step):
    track = _track()
    out = coarsen_times(track, resolution)
    assert np.array_equal(out.time, np.floor(track.time / step) * step)
    assert np.all(out.time <= track.time) and np.all(track.time - out.time < step)
    assert out.segments == track.segments and out.meta == track.meta
    assert np.array_equal(out.lat, track.lat) and np.array_equal(out.hr, track.hr)


def test_day_floors_to_utc_midnight():
    out = coarsen_times(_track(), "day")
    assert np.all(out.time == T0 + 86400 * 3)


def test_unknown_resolution():
    with pytest.raises(ValueError, match="minute"):
        coarsen_times(_track(), "week")


def test_shift_times():
    track = _track()
    out = shift_times(track, -3600.5)
    assert np.array_equal(out.time, track.time - 3600.5)
    assert same_track(shift_times(track, 0), track)
    with pytest.raises(ValueError):
        shift_times(track, float("nan"))
