"""Tracks against areas: time inside, crossings, closest pass, extent and presence days.

The "countries" are synthetic squares straddling the equator near 20°W, in open ocean; along the
equator a great circle is a line of latitude, so crossing times are exact.
"""

import datetime as dt

import numpy as np
import pytest

from placewise.geo import haversine
from placewise.model import BBox, DayPresence, Feature, Outline, PresenceDays
from placewise.tracks import Track
from placewise.tracks.spatial import bbox, closest_pass, crossings, presence_days, time_inside

T0 = 1.8e9


def _square(west, east, south=-1.0, north=1.0):
    return Outline((((south, west), (south, east), (north, east), (north, west)),))


A = Feature(outlines=(_square(-21.0, -20.0),), properties={"code": "AA"})
B = Feature(outlines=(_square(-20.0, -19.0),), properties={"code": "BB"})


def _equator(lon0, dlon, n, step_s=600.0, t0=T0, segments=None):
    return Track(
        time=t0 + np.arange(n) * step_s, lat=np.zeros(n), lon=lon0 + dlon * np.arange(n), segments=segments
    )


def test_time_inside_a_square_crossed_at_constant_speed():
    square = _square(-20.6, -19.7, south=-0.5, north=0.5)
    track = _equator(-21.0, 1 / 6, 13)  # 2 degrees of longitude in 2 hours
    expected = 0.9 / 2.0 * 7200
    assert time_inside(track, square) == pytest.approx(expected, abs=1e-3)
    assert time_inside(track, Feature(outlines=(square,))) == pytest.approx(expected, abs=1e-3)


def test_time_inside_never_counts_across_a_segment_break():
    square = _square(-20.6, -19.7, south=-0.5, north=0.5)
    split = _equator(-21.0, 1 / 6, 13, segments=(0, 6))  # the 10-minute step 5 -> 6 is inside the square
    assert time_inside(split, square) == pytest.approx(3240 - 600, abs=1e-3)
    assert time_inside(_equator(-30.0, 0.1, 10), square) == 0.0


def test_crossing_between_adjacent_squares_at_the_interpolated_time():
    track = _equator(-20.95, 0.15, 13)  # reaches -20 at step 6.333, so 3800 s in
    (crossing,) = crossings(track, [A, B])
    time, origin, dest = crossing
    assert time == pytest.approx(T0 + 3800, abs=1e-3)
    assert (origin, dest) == (0, 1)


def test_entering_crossing_and_leaving():
    track = _equator(-21.22, 0.15, 18)
    found = crossings(track, [A, B])
    assert [(c.from_index, c.to_index) for c in found] == [(-1, 0), (0, 1), (1, -1)]
    np.testing.assert_allclose([c.time - T0 for c in found], [880, 4880, 8880], atol=1e-3)


def test_closest_pass_between_fixes():
    track = _equator(-20.95, 0.15, 13)
    time, distance_km, index = closest_pass(track, 0.1, -20.0)
    assert time == pytest.approx(T0 + 3800, abs=1e-3)
    assert distance_km == pytest.approx(haversine(0.1, -20.0, 0.0, -20.0), rel=1e-9)
    assert index == 6
    # exactly on a fix
    time, distance_km, index = closest_pass(track, 0.0, -20.95)
    assert (time, index) == (T0, 0) and distance_km == pytest.approx(0, abs=1e-9)


def test_closest_pass_ignores_the_jump_across_a_segment_break():
    track = Track(time=T0 + np.arange(4.0), lat=[0.0, 0.0, 0.0, 0.0], lon=[-21, -20.9, -19.1, -19.0])
    _, distance_km, index = closest_pass(track, 0.0, -20.0)
    assert distance_km == pytest.approx(0, abs=1e-9) and index == 1
    split = Track.from_columns({"time": track.time, "lat": track.lat, "lon": track.lon}, segments=(0, 2))
    _, distance_km, index = closest_pass(split, 0.0, -20.0)
    assert distance_km == pytest.approx(haversine(0, -20, 0, -20.9), rel=1e-9) and index in (1, 2)


def test_bbox_and_the_antimeridian():
    track = Track(time=T0 + np.arange(3.0), lat=[-1.0, 0.5, 2.0], lon=[-20.0, -21.0, -19.5])
    assert bbox(track) == BBox(-1.0, -21.0, 2.0, -19.5)
    pacific = Track(time=T0 + np.arange(3.0), lat=[0.0, 0.1, 0.2], lon=[179.9, -179.95, -179.8])
    box = bbox(pacific)
    assert box == BBox(0.0, 179.9, 0.2, -179.8)
    assert box.crosses_antimeridian


def _utc(*args):
    return dt.datetime(*args, tzinfo=dt.timezone.utc).timestamp()


DAY = _utc(2027, 1, 15)
CODES = ["AA", "BB"]


def _one_day_crossing():
    """10:00 to 16:00 UTC, east from AA into BB, crossing -20 at about 12:08."""
    return _equator(-20.5, 1.4 / 36, 37, step_s=600, t0=DAY + 10 * 3600)


def test_presence_any_part_counts_both_countries_on_the_crossing_day():
    track = _one_day_crossing()
    result = presence_days(track, [A, B], CODES)
    assert isinstance(result, PresenceDays)
    assert (result.by, result.rule) == ("country", "any_part")
    (day,) = result.days
    assert isinstance(day, DayPresence)
    assert day.date == dt.date(2027, 1, 15)
    assert day.codes == ("AA", "BB")
    assert day.first_fix == dt.datetime(2027, 1, 15, 10, tzinfo=dt.timezone.utc)
    assert day.last_fix == dt.datetime(2027, 1, 15, 16, tzinfo=dt.timezone.utc)
    assert result.totals() == {"AA": 1, "BB": 1}


def test_presence_slept_and_majority_pick_one_country():
    track = _one_day_crossing()
    (slept,) = presence_days(track, [A, B], CODES, rule="slept").days
    assert slept.codes == ("BB",)  # the last fix before 03:00 the next morning
    (most,) = presence_days(track, [A, B], CODES, rule="majority").days
    assert most.codes == ("BB",)  # about 2 h in AA, 4 h in BB


def test_presence_slept_counts_the_night_for_the_evening_before():
    # in AA until 02:00 on the 16th, then in BB from 05:00: the night of the 15th was spent in AA
    t = DAY + np.array([20, 22, 26, 29, 31]) * 3600.0
    track = Track(time=t, lat=np.zeros(5), lon=[-20.5, -20.5, -20.5, -19.5, -19.5])
    days = presence_days(track, [A, B], CODES, rule="slept").days
    assert [(d.date, d.codes) for d in days] == [
        (dt.date(2027, 1, 15), ("AA",)),
        (dt.date(2027, 1, 16), ("BB",)),
    ]


def test_presence_uses_local_days_when_offsets_are_given():
    track = _one_day_crossing()  # 10:00-16:00 UTC is 23:00 on the 14th to 05:00 on the 15th at UTC-11
    offsets = np.full(len(track), -11 * 3600.0)
    result = presence_days(track, [A, B], CODES, tz_offsets_s=offsets)
    assert [(d.date, d.codes) for d in result.days] == [
        (dt.date(2027, 1, 14), ("AA",)),
        (dt.date(2027, 1, 15), ("AA", "BB")),
    ]
    first = result.days[0].first_fix
    assert first.utcoffset() == dt.timedelta(hours=-11) and first.hour == 23


def test_presence_validates_its_inputs():
    track = _one_day_crossing()
    with pytest.raises(ValueError):
        presence_days(track, [A, B], ["AA"])
    with pytest.raises(ValueError):
        presence_days(track, [A, B], CODES, rule="midnight")
