"""Smoothing: positions by a Kalman filter and Rauch-Tung-Striebel smoother, elevation by a Hampel
filter. Pure functions Track -> new Track: only the smoothed column changes; times, other columns,
segments and meta are carried over, and inputs are never modified.
"""

import math

import numpy as np

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.constants.tracks import (
    DEFAULT_ACCURACY_M,
    ELEVATION_WINDOW,
    HAMPEL_N_SIGMA,
    KALMAN_PROCESS_NOISE,
)
from placewise.geo._arrays import wrap_lon

from .._ops import M_PER_KM, bounds, nanmedian_rows, replace, segment_ids, windows

_M_PER_DEG = math.radians(MEAN_RADIUS_KM * M_PER_KM)
_MAD_TO_SIGMA = 1.4826  # median absolute deviation -> standard deviation, for Gaussian noise
_INITIAL_SPEED_VAR = 1e4  # (100 m/s)²: an all-but-uninformative prior on the starting velocity


def smooth(
    track,
    method="kalman",
    process_noise=KALMAN_PROCESS_NOISE,
    default_accuracy_m=DEFAULT_ACCURACY_M,
):
    """Smoothed positions; other columns, segments and meta unchanged.

    "kalman": a constant-velocity Kalman filter followed by a Rauch-Tung-Striebel smoother, run
    per segment in local metres (an equirectangular plane around the segment). Each fix's
    standard error is its `accuracy` when present, else default_accuracy_m; process_noise is the
    random-acceleration spectral density in m²/s³ (larger follows turns more tightly, smaller
    smooths harder). The smoother uses the whole segment, past and future, so it does not lag."""
    if method != "kalman":
        raise ValueError(f"unknown smoothing method {method!r}; use 'kalman'")
    lat, lon = track.lat.copy(), track.lon.copy()
    sigma = np.full(len(track), float(default_accuracy_m))
    if track.accuracy is not None:
        acc = track.accuracy
        sigma = np.where(np.isfinite(acc) & (acc > 0), acc, sigma)
    for start, end in bounds(track):
        if end - start < 2:
            continue
        sl = slice(start, end)
        lat0, lon0 = float(np.mean(lat[sl])), float(lon[start])
        kx = math.cos(math.radians(lat0)) * _M_PER_DEG
        x, y = wrap_lon(lon[sl] - lon0) * kx, (lat[sl] - lat0) * _M_PER_DEG
        xs, ys = _kalman_rts(track.time[sl], x, y, sigma[sl] ** 2, float(process_noise))
        lat[sl] = np.clip(lat0 + ys / _M_PER_DEG, -90.0, 90.0)
        lon[sl] = wrap_lon(lon0 + xs / kx)
    return replace(track, lat=lat, lon=lon)


def _kalman_rts(t, zx, zy, r, q):
    """Smoothed x and y for measurements zx, zy (m) at times t with variances r.

    x and y have independent dynamics and share the measurement variance, so their covariances
    are identical: one 2x2 [position, velocity] covariance recursion serves both axes. The
    recursion is inherently sequential, so it runs on plain floats rather than numpy scalars."""
    n = len(t)
    t, zx, zy, r = t.tolist(), zx.tolist(), zy.tolist(), r.tolist()
    # start at the first fix, heading as the first leg does (an exact guess on clean data, so a
    # straight path comes back unmoved), with a wide velocity variance so noise there is forgiven
    dt0 = t[1] - t[0]
    vx, vy = ((zx[1] - zx[0]) / dt0, (zy[1] - zy[0]) / dt0) if dt0 > 0 else (0.0, 0.0)
    x, y = zx[0], zy[0]
    p00, p01, p11 = r[0], 0.0, _INITIAL_SPEED_VAR
    fx, fvx, fy, fvy = [x], [vx], [y], [vy]  # filtered states
    f00, f01, f11 = [p00], [p01], [p11]  # filtered covariances
    a00s, a01s, a11s = [0.0], [0.0], [0.0]  # predicted covariances (index k: predicted for k)
    for k in range(1, n):
        dt = t[k] - t[k - 1]
        x += dt * vx
        y += dt * vy
        qdt = q * dt
        a00 = p00 + dt * (2 * p01 + dt * p11) + qdt * dt * dt / 3
        a01 = p01 + dt * p11 + qdt * dt / 2
        a11 = p11 + qdt
        s = a00 + r[k]
        k0, k1 = a00 / s, a01 / s
        ix, iy = zx[k] - x, zy[k] - y
        x += k0 * ix
        vx += k1 * ix
        y += k0 * iy
        vy += k1 * iy
        p00, p01, p11 = (1 - k0) * a00, (1 - k0) * a01, a11 - k1 * a01
        fx.append(x)
        fvx.append(vx)
        fy.append(y)
        fvy.append(vy)
        f00.append(p00)
        f01.append(p01)
        f11.append(p11)
        a00s.append(a00)
        a01s.append(a01)
        a11s.append(a11)

    # RTS gains C_k = P_k F^T inv(P_pred_{k+1}) depend only on covariances: compute them at once
    dt = np.diff(np.asarray(t))
    f00_, f01_, f11_ = (np.asarray(v[:-1]) for v in (f00, f01, f11))
    a00_, a01_, a11_ = (np.asarray(v[1:]) for v in (a00s, a01s, a11s))
    det = a00_ * a11_ - a01_ * a01_
    b00, b01, b10, b11 = f00_ + dt * f01_, f01_, f01_ + dt * f11_, f11_
    c00 = ((b00 * a11_ - b01 * a01_) / det).tolist()
    c01 = ((b01 * a00_ - b00 * a01_) / det).tolist()
    c10 = ((b10 * a11_ - b11 * a01_) / det).tolist()
    c11 = ((b11 * a00_ - b10 * a01_) / det).tolist()
    dt = dt.tolist()

    sx, svx, sy, svy = fx[-1], fvx[-1], fy[-1], fvy[-1]
    out_x, out_y = [0.0] * n, [0.0] * n
    out_x[-1], out_y[-1] = sx, sy
    for k in range(n - 2, -1, -1):
        h = dt[k]
        ex, evx = sx - (fx[k] + h * fvx[k]), svx - fvx[k]  # smoothed minus predicted, at k + 1
        ey, evy = sy - (fy[k] + h * fvy[k]), svy - fvy[k]
        sx = fx[k] + c00[k] * ex + c01[k] * evx
        svx = fvx[k] + c10[k] * ex + c11[k] * evx
        sy = fy[k] + c00[k] * ey + c01[k] * evy
        svy = fvy[k] + c10[k] * ey + c11[k] * evy
        out_x[k], out_y[k] = sx, sy
    return np.array(out_x), np.array(out_y)


def smooth_elevation(track, window=ELEVATION_WINDOW, n_sigma=HAMPEL_N_SIGMA):
    """Elevation outliers replaced, per segment, by a Hampel filter: a point further than n_sigma
    robust standard deviations from the median of the `window` points centred on it (odd) takes
    that median. n_sigma=None gives a plain running median instead. NaN stays NaN; a track
    without elevation comes back unchanged."""
    if window < 1 or window % 2 == 0:
        raise ValueError(f"window must be a positive odd number of points, not {window}")
    ele = track.ele
    if ele is None or len(track) == 0:
        return track[:]
    w = windows(ele, segment_ids(track), window)
    med = nanmedian_rows(w)
    if n_sigma is None:
        new = np.where(np.isnan(ele), ele, med)
    else:
        mad = nanmedian_rows(np.abs(w - med[:, None]))
        with np.errstate(invalid="ignore"):
            new = np.where(np.abs(ele - med) > n_sigma * _MAD_TO_SIGMA * mad, med, ele)
    return replace(track, ele=new)
