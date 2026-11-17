"""Thresholds and defaults for cleaning and measuring tracks. Every one is a keyword argument on the
function that uses it; these are the values used when the caller doesn't say."""

# -- clean --------------------------------------------------------------------------------------

# Plausible recording times, UTC unix seconds. Nothing has a GPS fix before the GPS epoch
# (1980-01-06); a device clock may run a little ahead, so allow a day past "now".
MIN_PLAUSIBLE_TIME = 315_964_800.0
FUTURE_TOLERANCE_S = 86_400.0

# A spike must look impossible on both legs (faster than this, and longer than the jump) while
# its neighbours agree. Genuine fast travel survives because steady motion makes the bypass
# speed just as high, so the threshold can sit well below airliner speeds.
SPIKE_MAX_SPEED_KMH = 200.0
SPIKE_MIN_JUMP_M = 50.0  # smaller excursions are ordinary jitter, for smooth() to handle
# Excursions of up to this many consecutive fixes (multipath often holds a bad fix for 2-3 s);
# longer detours are treated as real, since the bypass test alone can't tell them apart.
SPIKE_MAX_POINTS = 3

# A pause this long between fixes means the recording stopped (signal loss, auto-pause, a ride
# stitched from two files), so a new segment starts.
GAP_SPLIT_S = 300.0

# A point further than this from the track's median time (plus twice its interquartile time span,
# so multi-day recordings keep their ends) is a clock fault: GPS week rollover, a reset to 1970.
CLOCK_JUMP_MAX_OFFSET_S = 86_400.0

# Constant-velocity Kalman filter. Process noise is the spectral density of the random
# acceleration (m²/s³): ~1 follows walking, running, cycling and urban driving turns without
# lagging. Accuracy, when the track lacks it, is a typical open-sky phone fix (1-sigma, m).
KALMAN_PROCESS_NOISE = 1.0
DEFAULT_ACCURACY_M = 5.0

# Hampel filter on elevation: points per (odd) window, and how many robust standard deviations
# (1.4826 x the median absolute deviation) make an outlier.
ELEVATION_WINDOW = 7
HAMPEL_N_SIGMA = 3.0

THIN_EVERY_S = 10.0
THIN_EVERY_M = 50.0

# -- measure ------------------------------------------------------------------------------------

# Below a slow shuffle (0.5 m/s) a leg counts as stopped
MOVING_SPEED_KMH = 1.8

# Gain/loss only counts a climb or descent once it exceeds this, so GPS / barometric noise on
# flat ground adds nothing. 5 m suits GPS altitude; barometric altimeters can go to 1-2 m.
ELEVATION_HYSTERESIS_M = 5.0

# Max speed is the largest rolling median of this many consecutive leg speeds, so a single bad
# fix (a 1-leg spike) cannot set it.
MAX_SPEED_WINDOW = 5

# Grade is rise over run across this much distance centred on each point; shorter windows turn
# altitude noise into wild percentages.
GRADE_WINDOW_M = 100.0

SPLIT_KM = 1.0
BEST_EFFORT_KM = (1.0, 5.0, 10.0)

# Lower bounds of heart-rate zones as fractions of max HR (the common five-zone model, 50-100 %);
# time below the first bound is reported as zone 0.
HR_ZONES = (0.5, 0.6, 0.7, 0.8, 0.9)
