"""Thresholds and defaults for track operations: cleaning, measuring, interpolation and geotagging,
stays, travel modes, flights and presence days. Every one is a keyword argument on the
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

# --- interpolation and geotagging -------------------------------------------------------------

# Beyond 30 minutes without a fix a position between them is a guess; exiftool's geotagger uses
# the same limit (GeoMaxIntSecs = 1800).
MAX_INTERP_GAP_S = 1800.0

# Camera clocks are most often wrong by a time zone (UTC-12 .. UTC+12) plus minutes of drift.
CLOCK_SEARCH_S = (-12 * 3600.0, 12 * 3600.0)
CLOCK_COARSE_STEP_S = 60.0  # scan the whole range at this step, then refine
CLOCK_FINE_STEP_S = 1.0  # camera timestamps carry whole seconds
# A photo's own GPS agrees with the track when within this; phone GPS error plus a few seconds
# of walking between the photo and the fix.
CLOCK_GOOD_RESIDUAL_M = 100.0
# Without photo GPS, a photo is plausible this close to a fix even outside interpolation range:
# just before a recording starts or just after it stops.
CLOCK_NEAR_FIX_S = 300.0

# Where a step crosses an area's edge is found by bisection along the great circle; each round
# halves the uncertainty, so 40 pin it to 1e-12 of a step (microseconds even for an hour-long step).
BOUNDARY_BISECTIONS = 40

# --- stays ------------------------------------------------------------------------------------

STAY_RADIUS_M = 100.0  # GPS wander indoors plus walking around a building or a park
STAY_MIN_DURATION_S = 600.0  # 10 minutes: shorter pauses are traffic lights and queues
# A phone that went quiet and woke up in the same place stayed there, up to a day; longer
# silences are a powered-off phone and say nothing about where it was.
STAY_MAX_BRIDGE_S = 24 * 3600.0

# --- travel modes -----------------------------------------------------------------------------

MODES = ("walk", "bike", "drive", "flight", "gap")
# Speeds are measured over at least this long, so GPS jitter of a few metres between fixes
# can't make a person standing still look like a cyclist; modes shorter than this are merged
# into their neighbours.
MODE_WINDOW_S = 120.0
WALK_MAX_KMH = 7.0  # brisk walking is ~6 km/h; jogging overlaps cycling either way
BIKE_MAX_KMH = 25.0  # typical commuting cyclist; above it, motorised
# Airborne needs this speed both over the window before and the window after a step: no road
# vehicle sustains it, and a single bad fix only inflates one side.
AIRBORNE_MIN_KMH = 200.0
GAP_S = 2 * 3600.0  # a step longer than this is not movement we can classify

# --- flights ----------------------------------------------------------------------------------

# Silent jumps (the phone off in flight mode): this far within JUMP_WITHIN_S is a flight; past
# it the traveller could have driven or taken a train.
JUMP_KM = 800.0
JUMP_WITHIN_S = 48 * 3600.0
JUMP_ANY_KM = 3000.0  # this far is a flight however long the silence (or an ocean crossing)

# --- presence days ----------------------------------------------------------------------------

SLEPT_HOUR = 3  # local hour by which most people are where they sleep; the night belongs to the day before
