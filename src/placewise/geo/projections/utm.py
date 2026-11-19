"""UTM, UPS and MGRS on WGS84 (the rules are in the package's docstring): Karney's (2011) Krüger
series for the transverse Mercator, the polar stereographic UPS, and MGRS references over both."""

import math
import re

import numpy as np

from placewise.constants import utm as _g
from placewise.constants.wgs84 import A_M, E2, F

from .._arrays import as_floats, out, wrap_lon

_E = math.sqrt(E2)
_TM_SCALE = _g.UTM_K0 * _g.RECTIFYING_RADIUS_M
# distance from the pole in UPS is 2 k0 a / c * tan(pi/4 - chi/2), chi the conformal latitude
_UPS_SCALE = 2 * _g.UPS_K0 * A_M / ((1 - F) * math.exp(_E * math.atanh(_E)))


# --- UTM ---


def to_utm(lat, lon, zone=None):
    """(zone, hemisphere "N"/"S", easting_m, northing_m). The zone follows the standard rule,
    including the Norway (32V) and Svalbard (31X-37X) exceptions, unless `zone` forces one.
    Raises ValueError outside -80 <= lat < 84, where UPS applies (see `to_utm_ups`)."""
    lat, lon = np.broadcast_arrays(*as_floats(lat, lon))
    if not np.all((lat >= _g.UTM_MIN_LAT) & (lat < _g.UTM_MAX_LAT)):
        raise ValueError(
            f"UTM covers latitudes {_g.UTM_MIN_LAT:g} <= lat < {_g.UTM_MAX_LAT:g}; "
            "use to_ups or to_utm_ups for the polar caps (UPS)"
        )
    zone = _standard_zone(lat, lon) if zone is None else np.broadcast_to(_zones(zone), lat.shape)
    lam = np.radians(wrap_lon(lon - _central_meridian(zone)))
    x, y = _tm_forward(np.radians(lat), lam)
    north = lat >= 0
    easting = _g.UTM_FALSE_EASTING_M + x
    northing = y + np.where(north, 0.0, _g.UTM_FALSE_NORTHING_SOUTH_M)
    return _out_int(zone), _out_str(np.where(north, "N", "S")), out(easting), out(northing)


def from_utm(zone, hemisphere, easting, northing):
    """(lat, lon) of a UTM coordinate; hemisphere is "N" or "S" (any case)."""
    zone, north = _zones(zone), _north(hemisphere)
    easting, northing = as_floats(easting, northing)
    x = easting - _g.UTM_FALSE_EASTING_M
    y = northing - np.where(north, 0.0, _g.UTM_FALSE_NORTHING_SOUTH_M)
    lat, lam = _tm_inverse(x, y)
    return out(lat), out(wrap_lon(_central_meridian(zone) + np.degrees(lam)))


# --- UPS ---


def to_ups(lat, lon):
    """(hemisphere, easting_m, northing_m) in Universal Polar Stereographic, the grid for
    lat >= 84 and lat < -80. The pole is taken from the sign of lat; the maths holds anywhere
    except the opposite pole, though only the polar caps are standard UPS."""
    lat, lon = np.broadcast_arrays(*as_floats(lat, lon))
    north = lat >= 0
    polar_lat = np.where(north, lat, -lat)
    taup = _taupf(np.tan(np.radians(polar_lat)))
    # tan(pi/4 - chi/2) written to avoid cancellation on either side of the equator
    s = np.hypot(1.0, taup) + np.abs(taup)
    rho = np.where(taup >= 0, 1.0 / s, s)
    rho = _UPS_SCALE * np.where(polar_lat == 90, 0.0, rho)
    lam = np.radians(lon)
    easting = _g.UPS_FALSE_EASTING_M + rho * np.sin(lam)
    northing = _g.UPS_FALSE_NORTHING_M + np.where(north, -rho, rho) * np.cos(lam)
    return _out_str(np.where(north, "N", "S")), out(easting), out(northing)


def from_ups(hemisphere, easting, northing):
    """(lat, lon) of a UPS coordinate; hemisphere is "N" or "S" (any case)."""
    north = _north(hemisphere)
    easting, northing = as_floats(easting, northing)
    x, y = easting - _g.UPS_FALSE_EASTING_M, northing - _g.UPS_FALSE_NORTHING_M
    t = np.hypot(x, y) / _UPS_SCALE
    with np.errstate(divide="ignore"):
        taup = (1.0 / t - t) / 2  # inf at the pole, where arctan below gives 90
    lat = np.degrees(np.arctan(_tauf(taup)))
    lon = np.degrees(np.arctan2(x, np.where(north, -y, y)))
    return out(np.where(north, lat, -lat)), out(lon)


def to_utm_ups(lat, lon):
    """(zone, hemisphere, easting_m, northing_m) in whichever grid is standard for the point:
    UTM for -80 <= lat < 84, otherwise UPS with zone 0."""
    lat, lon = np.broadcast_arrays(*as_floats(lat, lon))
    shape, lat, lon = lat.shape, lat.ravel(), lon.ravel()
    polar = ~((lat >= _g.UTM_MIN_LAT) & (lat < _g.UTM_MAX_LAT))
    zone = np.zeros(lat.shape, dtype=int)
    easting, northing = np.empty(lat.shape), np.empty(lat.shape)
    if np.any(~polar):
        zone[~polar], _, easting[~polar], northing[~polar] = to_utm(lat[~polar], lon[~polar])
    if np.any(polar):
        _, easting[polar], northing[polar] = to_ups(lat[polar], lon[polar])
    hemisphere = np.where(lat >= 0, "N", "S")
    return (
        _out_int(zone.reshape(shape)),
        _out_str(hemisphere.reshape(shape)),
        out(easting.reshape(shape)),
        out(northing.reshape(shape)),
    )


def from_utm_ups(zone, hemisphere, easting, northing):
    """(lat, lon) from a UTM coordinate, or a UPS one when zone is 0."""
    zone, north = _zones(zone, allow_ups=True), _north(hemisphere)
    easting, northing = as_floats(easting, northing)
    zone, north, easting, northing = np.broadcast_arrays(zone, north, easting, northing)
    shape = zone.shape
    zone, north, easting, northing = (a.ravel() for a in (zone, north, easting, northing))
    hemisphere = np.where(north, "N", "S")
    lat, lon = np.empty(zone.shape), np.empty(zone.shape)
    ups = zone == 0
    if np.any(~ups):
        u = ~ups
        lat[u], lon[u] = from_utm(zone[u], hemisphere[u], easting[u], northing[u])
    if np.any(ups):
        lat[ups], lon[ups] = from_ups(hemisphere[ups], easting[ups], northing[ups])
    return out(lat.reshape(shape)), out(lon.reshape(shape))


# --- MGRS ---


def to_mgrs(lat, lon, precision=5):
    """MGRS reference such as "17TPJ3008733442", with `precision` digits per axis (0 = the
    100 km square, 5 = 1 m). Digits are truncated, not rounded, so the reference names the
    cell containing the point. Arrays give an array of strings."""
    if isinstance(precision, bool) or not isinstance(precision, (int, np.integer)) or not 0 <= precision <= 5:
        raise ValueError("precision must be an integer from 0 (100 km) to 5 (1 m)")
    lat = np.asarray(lat, dtype=np.float64)
    zone, hemi, easting, northing = to_utm_ups(lat, lon)
    parts = np.broadcast_arrays(lat, zone, hemi, easting, northing)
    refs = [_mgrs(*point, int(precision)) for point in zip(*(np.ravel(a) for a in parts), strict=True)]
    result = np.array(refs).reshape(parts[0].shape)
    return str(result) if result.ndim == 0 else result


def from_mgrs(text, centre=True):
    """(lat, lon) of an MGRS reference's cell: its centre by default (as GeographicLib does, so
    the error is at most half a cell), or its south-west corner with centre=False. Spaces and
    lowercase are fine; 0 to 11 digits per axis; polar A/B/Y/Z references decode via UPS.
    Raises ValueError for anything malformed or inconsistent (e.g. a row outside its band)."""
    s = "".join(str(text).split()).upper()
    m = re.fullmatch(r"(\d{1,2})?([A-Z])([A-Z])([A-Z])(\d*)", s)
    if not m:
        raise ValueError(f"not an MGRS reference: {text!r}")
    zone_text, band, col, row, digits = m.groups()
    if len(digits) % 2 or len(digits) > 2 * _g.MGRS_MAX_DIGITS:
        raise ValueError(f"MGRS needs an even number of digits, at most {2 * _g.MGRS_MAX_DIGITS}: {text!r}")
    k = len(digits) // 2
    unit = 10.0 ** (5 - k)
    offset = unit / 2 if centre else 0.0
    de = int(digits[:k]) * unit + offset if k else offset
    dn = int(digits[k:]) * unit + offset if k else offset

    if zone_text is None:
        if band not in _g.MGRS_UPS_COLUMNS:
            raise ValueError(f"band {band} needs a UTM zone number; polar bands are A, B, Y, Z: {text!r}")
        cols, col0 = _g.MGRS_UPS_COLUMNS[band]
        rows, row0 = _g.MGRS_UPS_ROWS[band]
        if col not in cols or row not in rows:
            raise ValueError(f"square {col}{row} is not in polar band {band}: {text!r}")
        easting = (cols.index(col) + col0) * _g.MGRS_SQUARE_M + de
        northing = (rows.index(row) + row0) * _g.MGRS_SQUARE_M + dn
        return from_ups("N" if band in "YZ" else "S", easting, northing)

    zone = int(zone_text)
    if not 1 <= zone <= 60:
        raise ValueError(f"UTM zone must be 1-60: {text!r}")
    if band not in _g.MGRS_BANDS:
        raise ValueError(f"band {band} is not a UTM latitude band: {text!r}")
    cols = _g.MGRS_UTM_COLUMNS[(zone - 1) % 3]
    if col not in cols or row not in _g.MGRS_UTM_ROWS:
        raise ValueError(f"square {col}{row} does not exist in zone {zone}: {text!r}")
    easting = (cols.index(col) + 1) * _g.MGRS_SQUARE_M + de
    shift = _g.MGRS_UTM_EVEN_ZONE_ROW_SHIFT if zone % 2 == 0 else 0
    row_index = (_g.MGRS_UTM_ROWS.index(row) - shift) % len(_g.MGRS_UTM_ROWS)
    hemisphere = "N" if band >= "N" else "S"
    south = -80 + _g.MGRS_BAND_HEIGHT_DEG * _g.MGRS_BANDS.index(band)
    north = _g.UTM_MAX_LAT if band == "X" else south + _g.MGRS_BAND_HEIGHT_DEG
    # row letters repeat every 2000 km (about 18 degrees), so the band picks the one cycle whose
    # latitude fits; the 1 degree slack covers 100 km squares that straddle a band edge
    cycle = len(_g.MGRS_UTM_ROWS) * _g.MGRS_SQUARE_M
    for k in range(int(_g.UTM_FALSE_NORTHING_SOUTH_M // cycle)):
        northing = row_index * _g.MGRS_SQUARE_M + k * cycle + dn
        lat, lon = from_utm(zone, hemisphere, easting, northing)
        if south - 1 <= lat <= north + 1:
            return lat, lon
    raise ValueError(f"square {col}{row} does not fall in band {zone}{band}: {text!r}")


# --- internals ---


def _taupf(tau):
    """tan of the conformal latitude from tan of the geographic one (Karney 2011, eq. 7-9)."""
    tau1 = np.hypot(1.0, tau)
    sig = np.sinh(_E * np.arctanh(_E * tau / tau1))
    return np.hypot(1.0, sig) * tau - sig * tau1


def _tauf(taup):
    """Inverse of _taupf by Newton's method (Karney 2011, eq. 19-21); converges in 2-3 steps,
    and the starting guess is close enough that a fixed count suffices for every input."""
    e2m = 1 - E2
    finite = np.isfinite(taup)
    tp = np.where(finite, taup, 0.0)
    # near the poles tau ~ taup * exp(e atanh e); elsewhere taup / (1 - e^2) is the better start
    tau = np.where(np.abs(tp) > 70, tp * math.exp(_E * math.atanh(_E)), tp / e2m)
    for _ in range(5):
        taupa = _taupf(tau)
        tau = tau + (tp - taupa) * (1 + e2m * tau * tau) / (e2m * np.hypot(1.0, tau) * np.hypot(1.0, taupa))
    return np.where(finite, tau, taup)


def _tm_forward(phi, lam):
    """Transverse Mercator (x, y) metres, before false origins, for lam relative to the central
    meridian (Karney 2011, eq. 10-11 and 35)."""
    taup = _taupf(np.tan(phi))
    xip = np.arctan2(taup, np.cos(lam))
    etap = np.arcsinh(np.sin(lam) / np.hypot(taup, np.cos(lam)))
    xi, eta = xip, etap
    for j, alpha in enumerate(_g.KRUGER_ALPHA, start=1):
        xi = xi + alpha * np.sin(2 * j * xip) * np.cosh(2 * j * etap)
        eta = eta + alpha * np.cos(2 * j * xip) * np.sinh(2 * j * etap)
    return _TM_SCALE * eta, _TM_SCALE * xi


def _tm_inverse(x, y):
    """(lat degrees, lam radians from the central meridian) of transverse Mercator metres."""
    xi, eta = y / _TM_SCALE, x / _TM_SCALE
    xip, etap = xi, eta
    for j, beta in enumerate(_g.KRUGER_BETA, start=1):
        xip = xip - beta * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        etap = etap - beta * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    taup = np.sin(xip) / np.hypot(np.sinh(etap), np.cos(xip))
    lam = np.arctan2(np.sinh(etap), np.cos(xip))
    return np.degrees(np.arctan(_tauf(taup))), lam


def _standard_zone(lat, lon):
    ilon = np.floor(wrap_lon(lon)).astype(int)
    zone = (ilon + 186) // 6
    band = np.clip((np.floor(lat).astype(int) + 80) // 8, 0, len(_g.MGRS_BANDS) - 1)
    v, x = _g.MGRS_BANDS.index("V"), _g.MGRS_BANDS.index("X")
    zone = np.where((band == v) & (zone == 31) & (ilon >= 3), 32, zone)  # Norway: 32V widened west
    # Svalbard: X-band zones 32, 34, 36 dropped, odd zones widened to 9 or 12 degrees
    svalbard = (band == x) & (ilon >= 0) & (ilon < 42)
    return np.where(svalbard, 2 * ((ilon + 183) // 12) + 1, zone)


def _central_meridian(zone):
    return zone * _g.UTM_ZONE_WIDTH_DEG - 183.0


def _zones(zone, allow_ups=False):
    arr = np.asarray(zone)
    low = 0 if allow_ups else 1
    if arr.dtype.kind not in "iu" or np.any((arr < low) | (arr > 60)):
        raise ValueError(f"UTM zone must be an integer {low}-60, got {zone!r}")
    return arr.astype(int)


def _north(hemisphere):
    h = np.char.upper(np.asarray(hemisphere, dtype=str))
    if np.any((h != "N") & (h != "S")):
        raise ValueError(f'hemisphere must be "N" or "S", got {hemisphere!r}')
    return h == "N"


def _mgrs(lat, zone, hemisphere, easting, northing, precision):
    ix, iy = int(easting // _g.MGRS_SQUARE_M), int(northing // _g.MGRS_SQUARE_M)
    if zone == 0:
        east = easting >= _g.UPS_FALSE_EASTING_M
        band = ("Z" if east else "Y") if hemisphere == "N" else ("B" if east else "A")
        cols, col0 = _g.MGRS_UPS_COLUMNS[band]
        rows, row0 = _g.MGRS_UPS_ROWS[band]
        head = f"{band}{cols[ix - col0]}{rows[iy - row0]}"
    else:
        band = _g.MGRS_BANDS[min(int((math.floor(lat) + 80) // 8), len(_g.MGRS_BANDS) - 1)]
        col = _g.MGRS_UTM_COLUMNS[(zone - 1) % 3][ix - 1]
        shift = _g.MGRS_UTM_EVEN_ZONE_ROW_SHIFT if zone % 2 == 0 else 0
        row = _g.MGRS_UTM_ROWS[(iy + shift) % len(_g.MGRS_UTM_ROWS)]
        head = f"{zone}{band}{col}{row}"
    if precision == 0:
        return head
    unit = 10 ** (5 - precision)
    de = int((easting - ix * _g.MGRS_SQUARE_M) // unit)
    dn = int((northing - iy * _g.MGRS_SQUARE_M) // unit)
    return f"{head}{de:0{precision}d}{dn:0{precision}d}"


def _out_int(value):
    return int(value) if np.ndim(value) == 0 else value


def _out_str(value):
    return str(value) if np.ndim(value) == 0 else value
