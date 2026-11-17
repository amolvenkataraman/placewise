"""Geo-indistinguishability: planar Laplace noise (Andrés, Bordenabe, Chatzikokolakis and Palamidessi,
"Geo-Indistinguishability: Differential Privacy for Location-Based Systems", CCS 2013).

Each point moves in a uniformly random direction by a radius drawn from Gamma(2, 1/ε), the radial
law of the planar Laplacian with density ∝ exp(-ε·d). For one released point, any two true
locations d metres apart are at most a factor exp(ε·d) apart in how likely they make the output.

Ordinary random noise can be averaged away by asking again. Here the angle and radius come from
HMAC(key, the point's cell in a keyed grid about 1/ε wide), so a place always gets the same
displacement: re-releasing it, or releasing it in many tracks, gives the same answer every time.

What it does not hide, honestly:
- The guarantee is per released point. A track of n points in n different cells spends n·ε,
  and the route's shape, speed and timing survive: a noisy track still shows where you went.
- Points sharing a noise cell share a displacement, so their relative positions are exact; anyone
  who knows one true point in a cell learns the true positions of all the others in it.
- Points just across a cell boundary get unrelated noise, so a dense track jumps at boundaries.
- Changing ε or the key draws fresh noise; releases under several settings compose.
"""

import numpy as np

from placewise.constants.privacy import NOISE_CELL_SCALES
from placewise.geo import destination
from placewise.geo._arrays import as_floats, out

from .._common import check_key, keyed_uniforms
from .snap import cells

_NEWTON_STEPS = 60


def radius_quantile(p, epsilon_per_m):
    """Inverse CDF of the planar Laplacian's radius: the r (metres) with
    1 - (1 + εr)·exp(-εr) = p, for p in [0, 1). Equivalent to the Lambert W₋₁ closed form."""
    if not epsilon_per_m > 0:
        raise ValueError(f"epsilon_per_m must be positive, got {epsilon_per_m}")
    (p,) = as_floats(p)
    if np.any((p < 0) | (p >= 1)):
        raise ValueError("p must lie in [0, 1)")
    # solve ln(1 + x) - x = ln(1 - p) for x = εr. The left side is concave and decreasing, and
    # x0 = L + ln(1 + L) + 1 (L = -ln(1 - p)) always starts right of the root, so Newton's method
    # walks down to it monotonically without overshooting.
    target = np.log1p(-np.where(p == 0, 0.5, p))  # p = 0 is a double root at x = 0: answered below
    big_l = -target
    x = big_l + np.log1p(big_l) + 1.0
    for _ in range(_NEWTON_STEPS):
        step = (np.log1p(x) - x - target) / (-x / (1.0 + x))
        x = np.maximum(x - step, 0.0)
        if np.all(np.abs(step) <= 1e-15 * np.maximum(x, 1.0)):
            break
    return out(np.where(p == 0, 0.0, x) / epsilon_per_m)


def geo_indistinguishable(lat, lon, epsilon_per_m, key):
    """(lat, lon) moved by keyed planar Laplace noise with budget epsilon_per_m (per metre).
    Mean displacement 2/ε: ε = 0.01 moves points ~200 m."""
    key = check_key(key)
    if not epsilon_per_m > 0:
        raise ValueError(f"epsilon_per_m must be positive, got {epsilon_per_m}")
    epsilon_per_m = float(epsilon_per_m)
    lat, lon = np.broadcast_arrays(*as_floats(lat, lon))
    row, col, *_ = cells(lat, lon, NOISE_CELL_SCALES / epsilon_per_m, key, purpose="noise-cell")
    pairs, inverse = np.unique(np.stack([row.ravel(), col.ravel()], axis=1), axis=0, return_inverse=True)
    # ε is in the message: releases at different ε must draw independently, or two outputs on one
    # ray at a known distance ratio would pin the true point
    draws = np.array([keyed_uniforms(key, "noise", epsilon_per_m, int(r), int(c), n=2) for r, c in pairs])
    draws = draws[inverse.ravel()].reshape((*lat.shape, 2))
    bearing = draws[..., 0] * 360.0
    radius_m = np.asarray(radius_quantile(draws[..., 1], epsilon_per_m))
    new_lat, new_lon = destination(lat, lon, bearing, radius_m / 1000.0)
    return out(new_lat), out(new_lon)
