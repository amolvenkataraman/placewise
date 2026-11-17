"""Numbers behind placewise.privacy: keys, the noise grid, time steps, the audit and the presets."""

import math

from .earth import MEAN_RADIUS_KM

# HMAC-SHA256 keys shorter than this are guessable enough to brute-force the secret offsets
KEY_MIN_BYTES = 16

# a degree of latitude on the mean sphere; the local metric grids are built from it
METRES_PER_DEGREE = math.pi * MEAN_RADIUS_KM * 1000 / 180

# geo-indistinguishable noise is seeded per keyed grid cell this many noise scales (1/ε) wide:
# about the size of the displacement, so one place keeps one draw while distinct places get their own
NOISE_CELL_SCALES = 1.0

TIME_RESOLUTION_S = {"minute": 60.0, "hour": 3600.0, "day": 86400.0}

# audit: the clustering and what counts as home, work and a stop
AUDIT_CELL_M = 100.0  # about a building plot plus GPS scatter
AUDIT_STATIONARY_MPS = 0.5  # slower than a stroll: dwelling, not travelling
AUDIT_NIGHT_HOURS = (0, 6)  # local [start, end) hours when people are usually at home
AUDIT_WORK_HOURS = (9, 17)  # local [start, end) hours of a typical working day
AUDIT_WORK_WEEKDAYS = (0, 1, 2, 3, 4)  # Monday..Friday
AUDIT_MIN_ENDPOINTS = 2  # one endpoint is a place; two in one spot are a pattern
# evidence (nights, weekdays, endpoints) needed for each severity; below "medium" is "low"
AUDIT_SEVERITY = {"medium": 3, "high": 7}  # a few observations hint, a week's worth confirms

# Presets, as PrivacyPolicy field values. Zones are the user's own and get added per call.
#   public_share: strangers see it. Hide up to ~1 km of each end (500 m + up to 500 m secret), snap
#     to a keyed 100 m grid (street-level route, no doorsteps or fine detail), hour-level times.
#   friends: people who may know you, but posts get forwarded. A shorter 200 + 200 m trim keeps the
#     route accurate; minute-level times drop the second-by-second record.
#   research: aggregate analysis. Planar Laplace noise at ε = ln 4 / 200 m, Andrés et al.'s example
#     setting (an observer's odds between any two places 200 m apart shift by at most 4x; mean
#     displacement 2/ε ≈ 290 m), which
#     keeps densities and flows usable; 200 + 200 m trim; hour-level times.
PRESETS = {
    "public_share": {"trim_m": 500.0, "trim_jitter_m": 500.0, "snap_m": 100.0, "time_resolution": "hour"},
    "friends": {"trim_m": 200.0, "trim_jitter_m": 200.0, "time_resolution": "minute"},
    "research": {
        "trim_m": 200.0,
        "trim_jitter_m": 200.0,
        "noise_epsilon": math.log(4) / 200.0,
        "time_resolution": "hour",
    },
}
