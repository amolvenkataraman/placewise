import math
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from placewise.geo import sun as s

UTC = timezone.utc
# public city centres only
TORONTO = (43.6532, -79.3832)  # Nathan Phillips Square
QUITO = (-0.1807, -78.4678)  # historic centre
TROMSO = (69.6492, 18.9553)  # city centre

# USNO rounds to the minute and the NOAA equations are good to about a minute
TWO_MINUTES = timedelta(minutes=2)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def assert_near(actual, expected, tolerance=TWO_MINUTES):
    assert actual is not None
    assert actual.tzinfo is not None
    assert abs(actual - expected) <= tolerance, f"{actual} vs {expected}"


def test_toronto_summer_solstice_matches_usno():
    # USNO Astronomical Applications, rstt/oneday API, coords=43.6532,-79.3832, tz=0:
    #   date=2026-06-21: Begin Civil Twilight 09:00, Rise 09:36, Upper Transit 17:19
    #   date=2026-06-22: Set 01:03, End Civil Twilight 01:39 (the evening of local June 21)
    # USNO "Table of Twilight Times for an Entire Year" (calculated/rstt/year), same point, UT:
    #   task=3 (nautical) June 21 begin 08:13, June 22 end 02:26
    #   task=4 (astronomical) June 21 begin 07:13, June 22 end 03:26
    t = s.sun_times(*TORONTO, date(2026, 6, 21))
    assert_near(t.astronomical_dawn, utc(2026, 6, 21, 7, 13))
    assert_near(t.nautical_dawn, utc(2026, 6, 21, 8, 13))
    assert_near(t.civil_dawn, utc(2026, 6, 21, 9, 0))
    assert_near(t.sunrise, utc(2026, 6, 21, 9, 36))
    assert_near(t.solar_noon, utc(2026, 6, 21, 17, 19))
    assert_near(t.sunset, utc(2026, 6, 22, 1, 3))
    assert_near(t.civil_dusk, utc(2026, 6, 22, 1, 39))
    assert_near(t.nautical_dusk, utc(2026, 6, 22, 2, 26))
    assert_near(t.astronomical_dusk, utc(2026, 6, 22, 3, 26))
    assert abs(t.day_length - timedelta(hours=15, minutes=27)) <= TWO_MINUTES


def test_quito_equinox_matches_usno():
    # USNO rstt/oneday API, date=2026-03-20, coords=-0.1807,-78.4678, tz=0:
    #   Rise 11:18, Upper Transit 17:21, Set 23:24
    t = s.sun_times(*QUITO, date(2026, 3, 20))
    assert_near(t.sunrise, utc(2026, 3, 20, 11, 18))
    assert_near(t.solar_noon, utc(2026, 3, 20, 17, 21))
    assert_near(t.sunset, utc(2026, 3, 20, 23, 24))
    assert abs(t.day_length - timedelta(hours=12, minutes=6)) <= TWO_MINUTES


def test_equator_equinox_noon_sun_is_overhead():
    # USNO rstt/oneday API, date=2026-03-20, coords=0,0: Upper Transit 12:07.
    # USNO celnav API, date=2026-03-20, time=12:07:00, coords=0,0: Sun hc 89.882767 (dec -0.04352)
    t = s.sun_times(0, 0, date(2026, 3, 20))
    assert_near(t.solar_noon, utc(2026, 3, 20, 12, 7))
    elevation, _ = s.sun_position(0, 0, utc(2026, 3, 20, 12, 7))
    assert elevation == pytest.approx(89.883, abs=0.05)
    noon_elevation, _ = s.sun_position(0, 0, t.solar_noon)
    assert noon_elevation > 89.9  # 90 minus that day's 0.04 deg of declination


def test_sun_position_vectorised_matches_usno():
    # USNO celnav API, date=2026-06-21, coords=43.6532,-79.3832, Sun hc (computed altitude, no
    # refraction) and zn (azimuth from true north):
    #   time=13:00:00 -> hc 33.834386, zn 88.722146
    #   time=17:19:00 -> hc 69.784079, zn 179.735223
    #   time=21:00:00 -> hc 40.841649, zn 264.37086
    times = np.array(["2026-06-21T13:00", "2026-06-21T17:19", "2026-06-21T21:00"], dtype="datetime64[s]")
    elevation, azimuth = s.sun_position(*TORONTO, times)
    assert elevation.shape == azimuth.shape == (3,)
    np.testing.assert_allclose(elevation, [33.834386, 69.784079, 40.841649], atol=0.05)
    np.testing.assert_allclose(azimuth, [88.722146, 179.735223, 264.37086], atol=0.05)

    unix = (times - np.datetime64(0, "s")) / np.timedelta64(1, "s")
    np.testing.assert_allclose(s.sun_position(*TORONTO, unix)[0], elevation)

    # points down a column, times along a row
    grid_elevation, _ = s.sun_position(np.array([[TORONTO[0]], [0.0]]), TORONTO[1], times)
    assert grid_elevation.shape == (2, 3)
    np.testing.assert_allclose(grid_elevation[0], elevation)


def test_scalar_inputs_give_floats_and_datetime_equals_unix_seconds():
    when = utc(2026, 6, 21, 13, 0)
    elevation, azimuth = s.sun_position(*TORONTO, when)
    assert type(elevation) is float and type(azimuth) is float
    assert s.sun_position(*TORONTO, when.timestamp()) == pytest.approx((elevation, azimuth))
    toronto_summer = timezone(timedelta(hours=-4))
    assert s.sun_position(*TORONTO, datetime(2026, 6, 21, 9, 0, tzinfo=toronto_summer)) == pytest.approx(
        (elevation, azimuth)
    )


def test_sun_is_at_the_horizon_at_published_sunrise():
    # USNO rstt/oneday: Toronto 2026-06-21 Rise 09:36 UT; USNO celnav at 09:36:00 gives hc -0.841683.
    # Sunrise is when the Sun's centre is 0.833 deg below the geometric horizon.
    sunrise = utc(2026, 6, 21, 9, 36)
    geometric, _ = s.sun_position(*TORONTO, sunrise)
    assert geometric == pytest.approx(-0.842, abs=0.05)
    apparent, _ = s.sun_position(*TORONTO, sunrise, refraction=True)
    assert geometric < apparent < 0 and math.isclose(apparent, 0, abs_tol=1)


def test_polar_night_tromso():
    # USNO rstt/oneday API, date=2026-12-21, coords=69.6492,18.9553, tz=0:
    #   "Object continuously below the Horizon", Begin Civil Twilight 08:31, End Civil Twilight 12:53
    t = s.sun_times(*TROMSO, date(2026, 12, 21))
    assert t.sunrise is None and t.sunset is None
    assert t.day_length == timedelta(0)
    assert_near(t.civil_dawn, utc(2026, 12, 21, 8, 31))
    assert_near(t.civil_dusk, utc(2026, 12, 21, 12, 53))
    # the noon Sun peaks near -3 deg, inside the golden-hour band, so it lasts through noon
    assert t.golden_hour_morning[1] == t.solar_noon == t.golden_hour_evening[0]


def test_polar_day_tromso():
    # USNO rstt/oneday API, date=2026-06-21, coords=69.6492,18.9553, tz=0:
    #   "Object continuously above the Horizon", "continuously above the Twilight Limit",
    #   Upper Transit 10:46
    t = s.sun_times(*TROMSO, date(2026, 6, 21))
    assert t.sunrise is None and t.sunset is None
    assert t.civil_dawn is None and t.nautical_dusk is None and t.astronomical_dawn is None
    assert t.blue_hour_morning is None and t.blue_hour_evening is None
    assert t.day_length == timedelta(hours=24)
    assert_near(t.solar_noon, utc(2026, 6, 21, 10, 46))


def test_golden_and_blue_hours_fit_together():
    t = s.sun_times(*TORONTO, date(2026, 6, 21))
    assert t.blue_hour_morning[0] == t.civil_dawn
    assert t.blue_hour_morning[1] == t.golden_hour_morning[0]
    assert t.golden_hour_evening[1] == t.blue_hour_evening[0]
    assert t.blue_hour_evening[1] == t.civil_dusk
    assert t.golden_hour_morning[0] < t.sunrise < t.golden_hour_morning[1]
    assert t.golden_hour_evening[0] < t.sunset < t.golden_hour_evening[1]
    assert s.sun_position(*TORONTO, t.golden_hour_morning[1])[0] == pytest.approx(6, abs=0.05)


def test_rejects_ambiguous_times():
    with pytest.raises(ValueError):
        s.sun_position(*TORONTO, datetime(2026, 6, 21, 12))  # naive: which zone?
    with pytest.raises(TypeError):
        s.sun_times(*TORONTO, utc(2026, 6, 21))
