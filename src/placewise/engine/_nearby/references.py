"""What is near a point: notable cities and, far offshore, the nearest country (the airport is
airports.py).

- near: up to NearSettings.max_near notable cities (NOTABLE_POPULATION+) within
  NearSettings.notable_rural, nearest first, across borders, without the chosen city.
- water: beyond TERRITORIAL_KM of every country, the country whose boundary is nearest (OFFSHORE)
  up to WATER_SEARCH_KM, with the exact distance and bearing to that boundary.
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.geo import compass, initial_bearing


def water(a, countries, lat, lon):
    """Fill a["water", "water_km", "water_at"] for points in no country."""
    n = len(lat)
    far = np.flatnonzero(a["cidx"] < 0)
    a["water"], a["water_km"] = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
    a["water_at"] = np.full((n, 2), np.nan)  # the nearest point of that country's boundary
    if countries is not None and len(far):
        f, d, at_lat, at_lon = countries.nearest_boundary(lat[far], lon[far], const.WATER_SEARCH_KM)
        a["water"][far], a["water_km"][far] = f, d
        a["water_at"][far] = np.column_stack([at_lat, at_lon])


def bearings(layer, lat, lon, rows, reverse=False):
    """(degrees, compass words) from each point to the point-layer row (or back with reverse);
    NaN and "" where the row is -1."""
    rows = np.asarray(rows)
    deg = np.full(len(rows), np.nan)
    words = np.full(len(rows), "", dtype=object)
    ok = np.flatnonzero(rows >= 0)
    if len(ok) and layer is not None:
        plat, plon = layer.lat[rows[ok]], layer.lon[rows[ok]]
        if reverse:
            b = np.atleast_1d(initial_bearing(plat, plon, lat[ok], lon[ok]))
        else:
            b = np.atleast_1d(initial_bearing(lat[ok], lon[ok], plat, plon))
        deg[ok] = b
        words[ok] = np.atleast_1d(compass(b, const.COMPASS_POINTS))
    return deg, words


def water_bearings(a, lat, lon):
    """Bearing from far-offshore points to the nearest point of their `water` country's boundary."""
    n = len(lat)
    deg, words = np.full(n, np.nan), np.full(n, "", dtype=object)
    far = np.flatnonzero(a["water"] >= 0)
    if len(far):
        at = a["water_at"][far]
        b = np.atleast_1d(initial_bearing(lat[far], lon[far], at[:, 0], at[:, 1]))
        deg[far], words[far] = b, np.atleast_1d(compass(b, const.COMPASS_POINTS))
    return deg, words


def near_rows(cities, a, lat, lon, city, max_near, near_km, also=None):
    """Per point, [(city row, km, bearing, compass), ...] for `near`, nearest first, leaving out
    the point's `city` row (and its `also` row: the city a town outline names)."""
    n = len(lat)
    if "notable" not in a or not max_near:
        return [()] * n
    notable = a["notable"].copy()
    notable[(notable == city[:, None]) | (a["notable_km"] > near_km)] = -1
    if also is not None:
        notable[notable == also[:, None]] = -1
    # keep the first max_near valid columns of each row
    rank = np.cumsum(notable >= 0, axis=1)
    notable[rank > max_near] = -1
    q, j = np.nonzero(notable >= 0)
    rows = notable[q, j]
    deg, word = bearings(cities, lat[q], lon[q], rows)
    out = [[] for _ in range(n)]
    for qi, row, km, d, w in zip(q.tolist(), rows.tolist(), a["notable_km"][q, j].tolist(), deg.tolist(),
                                 word.tolist(), strict=True):  # fmt: skip
        out[qi].append((row, km, d, w))
    return out


def km_text(km):
    return f"{km:.0f} km" if km >= 10 else f"{km:.1f} km"


_OPPOSITE = {"N": "S", "NE": "SW", "E": "W", "SE": "NW", "S": "N", "SW": "NE", "W": "E", "NW": "SE"}


def opposite(word):
    return _OPPOSITE.get(word, word)
