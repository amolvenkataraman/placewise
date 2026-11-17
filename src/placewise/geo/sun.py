"""Where the Sun is and when it rises, sets and passes the twilight angles, from the NOAA solar
position equations (the NOAA Solar Calculator and its spreadsheet, after Meeus, "Astronomical
Algorithms"). Good to about a minute for |lat| < 72°; nearer the poles the Sun crosses each angle so
slowly that small errors in its position become several minutes.

Elevations are of the Sun's centre above the geometric horizon, in degrees; the angles that define
sunrise, twilight and the golden and blue hours are in `placewise.constants.sun`.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import numpy as np

from placewise.constants.sun import (
    ASTRONOMICAL_TWILIGHT_DEG,
    BLUE_HOUR_DEG,
    CIVIL_TWILIGHT_DEG,
    DAYS_PER_JULIAN_CENTURY,
    GOLDEN_HOUR_DEG,
    J2000_JD,
    NAUTICAL_TWILIGHT_DEG,
    SUNRISE_ELEVATION_DEG,
    UNIX_EPOCH_JD,
)

from ._arrays import as_floats, out

_DAY_S = 86400.0
_HALF_DAY_S = 43200.0
_S_PER_DEG = 240.0  # the hour angle turns 360° a day, one degree every four minutes
_ITERATIONS = 4  # each pass re-evaluates the Sun at the latest estimate; three already converge

Window = tuple[datetime, datetime]


def sun_position(lat, lon, when, refraction=False):
    """(elevation, azimuth) of the Sun in degrees; azimuth 0 = north, 90 = east.

    `when` is a timezone-aware datetime (or a list of them), numpy datetime64 taken as UTC, or unix
    seconds; everything broadcasts. Elevation is geometric unless `refraction` adds NOAA's
    atmospheric refraction, which lifts the Sun by about half a degree at the horizon.
    """
    lat, lon, t = as_floats(lat, lon, _unix_seconds(when))
    decl, eot = _declination_and_eot(t)
    hour_angle = np.radians(_hour_angle(t, lon, eot))
    phi = np.radians(lat)
    sin_elev = np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.cos(hour_angle)
    elevation = np.degrees(np.arcsin(np.clip(sin_elev, -1.0, 1.0)))
    # measured from south towards west, then turned to start at north
    azimuth = np.degrees(
        np.arctan2(
            np.sin(hour_angle) * np.cos(decl),
            np.cos(hour_angle) * np.sin(phi) * np.cos(decl) - np.sin(decl) * np.cos(phi),
        )
    )
    azimuth = (azimuth + 180.0) % 360.0
    if refraction:
        elevation = elevation + _refraction(elevation)
    return out(elevation), out(np.broadcast_to(azimuth, elevation.shape))


@dataclass(frozen=True)
class SunTimes:
    """One place's solar day. Times are UTC datetimes; an event that does not happen is None.

    Each golden- and blue-hour window is (start, end), or None if the Sun never enters that band on
    that side of noon. A window the Sun is still in at solar noon or solar midnight ends (or starts)
    there, so the morning and evening windows always lie on their own side of noon.
    """

    solar_noon: datetime
    sunrise: datetime | None
    sunset: datetime | None
    civil_dawn: datetime | None
    civil_dusk: datetime | None
    nautical_dawn: datetime | None
    nautical_dusk: datetime | None
    astronomical_dawn: datetime | None
    astronomical_dusk: datetime | None
    golden_hour_morning: Window | None
    golden_hour_evening: Window | None
    blue_hour_morning: Window | None
    blue_hour_evening: Window | None
    day_length: timedelta  # time above the sunrise angle: 24 h in polar day, 0 in polar night


def sun_times(lat, lon, day):
    """Sunrise, sunset, twilight and the golden and blue hours at one place on one `datetime.date`.

    `day` is the date in local mean solar time (UTC + lon/15 hours), which is within about an hour
    of the civil date there, so the events are those around that day's solar noon even when they
    fall on another UTC date: Toronto's sunset on 21 June is at about 01:03 UTC on 22 June.
    """
    if isinstance(day, datetime) or not isinstance(day, date):
        raise TypeError("day must be a datetime.date; for a datetime, pass its .date() in the place's zone")
    lat, lon = float(lat), float(lon)
    midnight_utc = datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()
    noon = _solar_noon(lon, midnight_utc + _HALF_DAY_S - lon * _S_PER_DEG)

    def crossing(elevation, side):
        return _crossing(lat, lon, noon, elevation, side)

    def window(low, high, side):
        return _window(lat, lon, noon, low, high, side)

    golden_low, golden_high = GOLDEN_HOUR_DEG
    blue_low, blue_high = BLUE_HOUR_DEG
    daylight = [window(SUNRISE_ELEVATION_DEG, math.inf, side) for side in (-1, 1)]
    return SunTimes(
        solar_noon=_utc(noon),
        sunrise=_utc(crossing(SUNRISE_ELEVATION_DEG, -1)),
        sunset=_utc(crossing(SUNRISE_ELEVATION_DEG, 1)),
        civil_dawn=_utc(crossing(CIVIL_TWILIGHT_DEG, -1)),
        civil_dusk=_utc(crossing(CIVIL_TWILIGHT_DEG, 1)),
        nautical_dawn=_utc(crossing(NAUTICAL_TWILIGHT_DEG, -1)),
        nautical_dusk=_utc(crossing(NAUTICAL_TWILIGHT_DEG, 1)),
        astronomical_dawn=_utc(crossing(ASTRONOMICAL_TWILIGHT_DEG, -1)),
        astronomical_dusk=_utc(crossing(ASTRONOMICAL_TWILIGHT_DEG, 1)),
        golden_hour_morning=_utc_window(window(golden_low, golden_high, -1)),
        golden_hour_evening=_utc_window(window(golden_low, golden_high, 1)),
        blue_hour_morning=_utc_window(window(blue_low, blue_high, -1)),
        blue_hour_evening=_utc_window(window(blue_low, blue_high, 1)),
        day_length=timedelta(seconds=round(sum(end - start for start, end in filter(None, daylight)))),
    )


def _unix_seconds(when):
    if isinstance(when, datetime):
        return _aware_timestamp(when)
    values = np.asarray(when)
    if np.issubdtype(values.dtype, np.datetime64):
        return (values - np.datetime64(0, "s")) / np.timedelta64(1, "s")
    if values.dtype == object:
        return np.vectorize(_aware_timestamp, otypes=[np.float64])(values)
    return values


def _aware_timestamp(moment):
    # a naive datetime would silently take the computer's own zone
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("datetimes must be timezone-aware")
    return moment.timestamp()


def _declination_and_eot(t):
    """Solar declination (radians) and the equation of time (minutes) at unix seconds t."""
    jc = (t / _DAY_S + UNIX_EPOCH_JD - J2000_JD) / DAYS_PER_JULIAN_CENTURY
    mean_long = np.radians((280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0)
    mean_anom = np.radians(357.52911 + jc * (35999.05029 - 0.0001537 * jc))
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    centre = (
        np.sin(mean_anom) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + np.sin(2 * mean_anom) * (0.019993 - 0.000101 * jc)
        + np.sin(3 * mean_anom) * 0.000289
    )
    node = np.radians(125.04 - 1934.136 * jc)  # the Moon's node drives nutation
    apparent_long = np.radians(np.degrees(mean_long) + centre - 0.00569 - 0.00478 * np.sin(node))
    mean_obliq = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    obliq = np.radians(mean_obliq + 0.00256 * np.cos(node))
    decl = np.arcsin(np.sin(obliq) * np.sin(apparent_long))
    y = np.tan(obliq / 2) ** 2
    eot = 4.0 * np.degrees(
        y * np.sin(2 * mean_long)
        - 2 * ecc * np.sin(mean_anom)
        + 4 * ecc * y * np.sin(mean_anom) * np.cos(2 * mean_long)
        - 0.5 * y * y * np.sin(4 * mean_long)
        - 1.25 * ecc * ecc * np.sin(2 * mean_anom)
    )
    return decl, eot


def _hour_angle(t, lon, eot):
    """Degrees west of the local meridian, in [-180, 180): negative before noon."""
    true_solar_s = t % _DAY_S + eot * 60.0 + lon * _S_PER_DEG
    return (true_solar_s / _S_PER_DEG) % 360.0 - 180.0


def _refraction(elevation):
    """NOAA's refraction correction in degrees, piecewise in the true elevation."""
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        te = np.tan(np.radians(elevation))
        arcsec = np.select(
            [elevation > 85.0, elevation > 5.0, elevation > -0.575],
            [
                0.0,
                58.1 / te - 0.07 / te**3 + 0.000086 / te**5,
                1735.0
                + elevation * (-518.2 + elevation * (103.4 + elevation * (-12.79 + elevation * 0.711))),
            ],
            -20.774 / te,
        )
    return arcsec / 3600.0


def _sun(t, lon):
    decl, eot = _declination_and_eot(t)
    return float(decl), float(_hour_angle(t, lon, eot))


def _solar_noon(lon, guess):
    t = guess
    for _ in range(_ITERATIONS):
        t -= _sun(t, lon)[1] * _S_PER_DEG
    return t


def _elevation(lat, lon, t):
    return sun_position(lat, lon, t)[0]


def _crossing(lat, lon, noon, elevation, side):
    """Unix time the Sun's centre passes `elevation` before (side -1) or after (+1) noon, or None."""
    phi = math.radians(lat)
    t = noon
    for _ in range(_ITERATIONS):
        decl, hour_angle = _sun(t, lon)
        denominator = math.cos(phi) * math.cos(decl)
        if abs(denominator) < 1e-12:  # at a pole the Sun circles at one height all day
            return None
        cos_h0 = (math.sin(math.radians(elevation)) - math.sin(phi) * math.sin(decl)) / denominator
        if not -1.0 <= cos_h0 <= 1.0:  # the Sun stays above or below that height all day
            return None
        target = side * math.degrees(math.acos(cos_h0))
        # wrapped so an hour angle near ±180 (a crossing close to midnight) never jumps a day
        t += ((target - hour_angle + 180.0) % 360.0 - 180.0) * _S_PER_DEG
    return t


def _window(lat, lon, noon, low, high, side):
    """(start, end) unix times the Sun's elevation is within [low, high] on one side of noon, or None.

    On each half of the solar day the elevation only rises (morning) or falls (evening), so the
    band is one stretch, cut off at noon or midnight where the Sun never leaves it.
    """
    edge = noon + side * _HALF_DAY_S  # solar midnight
    at_noon, at_edge = _elevation(lat, lon, noon), _elevation(lat, lon, edge)
    if at_noon < low or at_edge > high:
        return None
    low_t = edge if at_edge >= low else _crossing(lat, lon, noon, low, side)
    high_t = noon if at_noon <= high else _crossing(lat, lon, noon, high, side)
    # the two tests above use the Sun's declination at noon and midnight, the crossings at their own
    # times; on the rare day they disagree, fall back to the edge of the half-day
    low_t = edge if low_t is None else low_t
    high_t = noon if high_t is None else high_t
    return (low_t, high_t) if side < 0 else (high_t, low_t)


def _utc(t):
    return None if t is None else datetime.fromtimestamp(round(t), tz=timezone.utc)


def _utc_window(pair):
    return None if pair is None else (_utc(pair[0]), _utc(pair[1]))
