"""Defaults for track operations: interpolation, geotagging, stays, travel modes, flights and
presence days. Every one is a parameter of the function that uses it."""

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
