"""Keyed grid snapping: report the centre of a grid cell instead of the point.

A public grid (rounding coordinates, geohash cells) has public boundaries: an observer who sees a
track hop from one cell to the next knows the exact moment it crossed a known line. Here the grid's
origin is secret: the latitude offset and each latitude row's longitude offset come from
HMAC(key, ...). Snapping is a pure function of the point and key, so the same place always gives
the same centre, and repeated releases can't be averaged back to the true point.

The grid is local and metric: rows cell_m metres tall, and in each row cells of cell_m metres
across at the row's central latitude (longitude spacing scaled by 1 / cos(lat)), so cells stay
roughly square at any latitude. Near the poles cells widen to whole rows; across the antimeridian
the last cell of a row is cut short.

What it does not hide: which cell you were in (the precision is cell_m by design), and the grid
itself where released points are dense (every distinct centre reveals its cell's boundaries; rows
have independent offsets, so this doesn't carry from one row to another). Movement within a cell
is erased, but the time spent in each cell and the order of cells are not.
"""

import numpy as np

from placewise.constants.privacy import METRES_PER_DEGREE
from placewise.geo._arrays import as_floats, out, wrap_lon

from .._common import check_key, keyed_uniforms, keyed_uniforms_each

_MIN_COS = 1e-12  # keeps polar rows finite; they become one cell wide


def keyed_snap(lat, lon, cell_m, key):
    """(lat, lon) of the centre of each point's cell in the keyed grid of cell_m-metre cells."""
    *_, centre_lat, centre_lon = cells(lat, lon, cell_m, check_key(key))
    return out(centre_lat), out(centre_lon)


def cells(lat, lon, cell_m, key, purpose="snap"):
    """(row, column, centre lat, centre lon) of each point in the keyed grid; `purpose` gives
    independent grids for independent uses of one key."""
    if not cell_m > 0:
        raise ValueError(f"cell size must be positive, got {cell_m}")
    lat, lon = np.broadcast_arrays(*as_floats(lat, lon))
    cell_m = float(cell_m)
    dlat = cell_m / METRES_PER_DEGREE
    lat_offset = keyed_uniforms(key, purpose + "-lat", cell_m)[0] * dlat
    row = np.floor((lat + 90.0 - lat_offset) / dlat).astype(np.int64)
    centre_lat = -90.0 + lat_offset + (row + 0.5) * dlat
    dlon = np.minimum(
        cell_m / (METRES_PER_DEGREE * np.maximum(np.cos(np.radians(centre_lat)), _MIN_COS)), 360.0
    )
    rows, inverse = np.unique(row, return_inverse=True)
    # one HMAC per distinct row, not per point
    offsets = keyed_uniforms_each(key, purpose + "-row", cell_m, rows=rows[:, None])
    row_offset = np.array([u[0] for u in offsets])
    lon_offset = row_offset[inverse.reshape(row.shape)] * dlon
    col = np.floor((lon + 180.0 - lon_offset) / dlon).astype(np.int64)
    centre_lon = wrap_lon(-180.0 + lon_offset + (col + 0.5) * dlon)
    return row, col, np.clip(centre_lat, -90.0, 90.0), centre_lon
