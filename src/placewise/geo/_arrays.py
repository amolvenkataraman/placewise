"""The scalar-or-array convention every toolkit function follows."""

import numpy as np


def as_floats(*values):
    """Each value as a float64 array (0-d for scalars), for broadcasting."""
    return tuple(np.asarray(v, dtype=np.float64) for v in values)


def out(value):
    """Plain float for a 0-d result, so scalar callers never see numpy types; arrays unchanged."""
    value = np.asarray(value)
    return float(value) if value.ndim == 0 else value


def wrap_lon(lon):
    """Longitude in [-180, 180)."""
    return (np.asarray(lon, dtype=np.float64) + 180.0) % 360.0 - 180.0
