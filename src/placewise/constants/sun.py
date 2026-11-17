"""Sun-angle conventions for sunrise, twilight and the photographers' hours, plus the time scale the
NOAA solar equations use. Angles are the elevation of the Sun's centre above the geometric
horizon, in degrees. Sources differ on several of these; the values below are the conventions
placewise uses."""

# The Sun's upper limb touching the horizon: 34′ of standard refraction plus a 16′ solar radius
# put the centre 50′ below it (the USNO and NOAA convention)
SUNRISE_ELEVATION_DEG = -0.833

CIVIL_TWILIGHT_DEG = -6.0
NAUTICAL_TWILIGHT_DEG = -12.0
ASTRONOMICAL_TWILIGHT_DEG = -18.0

# (low, high) bands; definitions in photography guides range from 0..+10 to -6..+6 for golden hour
GOLDEN_HOUR_DEG = (-4.0, 6.0)
BLUE_HOUR_DEG = (-6.0, -4.0)

# Julian dates of 1970-01-01T00:00Z and of J2000.0 (2000-01-01T12:00 TT), the epoch of the series
UNIX_EPOCH_JD = 2440587.5
J2000_JD = 2451545.0
DAYS_PER_JULIAN_CENTURY = 36525.0
