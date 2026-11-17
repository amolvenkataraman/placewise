"""Unit conversion for lengths and speeds (the factors live in placewise.constants)."""

from placewise.constants.distance import METRES_PER
from placewise.constants.speed import METRES_PER_SECOND

_UNITS = {
    **{u: ("length", f) for u, f in METRES_PER.items()},
    **{u: ("speed", f) for u, f in METRES_PER_SECOND.items()},
}


def convert(value, from_unit, to_unit):
    """Convert a length or speed (scalar or array) between units: "m", "km", "mi", "nmi", "ft",
    "m/s", "km/h", "mph", "kn"."""
    try:
        (dim_from, f_from), (dim_to, f_to) = _UNITS[from_unit], _UNITS[to_unit]
    except KeyError as e:
        raise ValueError(f"unknown unit {e.args[0]!r}; known: {', '.join(_UNITS)}") from None
    if dim_from != dim_to:
        raise ValueError(f"can't convert {dim_from} ({from_unit}) to {dim_to} ({to_unit})")
    return value * (f_from / f_to)
