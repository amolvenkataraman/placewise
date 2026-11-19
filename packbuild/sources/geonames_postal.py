"""GeoNames postal codes (export/zip/allCountries.zip, CC BY 4.0): the world-postal pack's `postal`
points, for the countries outside the country packs (constants.postal says which are left out and
why).

The file is one tab-separated row per code and place (country, code, place name, admin1-3 names
and codes, lat, lon, accuracy), about 1.8 million rows in 124 countries. Some countries keep only
part of their codes: the UK and the Netherlands their outward code and PC4 (the full codes are in
separate files), Chile, Ireland and Malta their first part, China codes ending in 00, Argentina
five characters, Brazil only major codes (GeoNames' readme).

- `keep` drops the countries placewise covers better or GeoNames sources nowhere, Northern
  Ireland's codes (BT), business-mail codes (CEDEX, Germany's large recipients) and impossible
  points.
- `points` drops exact repeats and placeholder points: a coordinate several codes share (a city's
  centre given to each of its codes beside the code's own point).
- `reaches` sizes how far each country's points answer a lookup, from their spacing.
- `postal_layer` writes one row per point: a code's first point is its primary row (the one the
  name index finds), its other places secondary rows that sharpen reverse lookups.
"""

import io
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from placewise.constants import postal as const
from placewise.packs import PointIndex

from ..layer import LayerData

SOURCE = "geonames"
MEMBER = "allCountries.txt"
_FIELDS = 11  # through the longitude


@dataclass(frozen=True, slots=True)
class Row:
    country: str
    code: str
    place: str
    lat: float
    lon: float
    accuracy: str = ""  # 1 estimated, 4 from a GeoNames place, 6 centre of addresses; "" not given


def read_rows(path):
    """Yield the Rows of a GeoNames postal file (a zip holding allCountries.txt, or a .txt), in
    file order; short lines and unreadable coordinates are skipped."""
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z, z.open(MEMBER) as raw:
            yield from _rows(io.TextIOWrapper(raw, encoding="utf-8"))
    else:
        with path.open(encoding="utf-8") as f:
            yield from _rows(f)


def _rows(lines):
    for line in lines:
        r = line.rstrip("\n").split("\t")
        if len(r) < _FIELDS:
            continue
        try:
            lat, lon = float(r[9]), float(r[10])
        except ValueError:
            continue
        accuracy = r[11].strip() if len(r) > _FIELDS else ""
        yield Row(r[0].strip(), r[1].strip(), r[2].strip(), lat, lon, accuracy)


def keep(row):
    """Whether a row may go in the pack (constants.postal: the countries, prefixes and business
    codes left out); points at a pole, off the globe or at 0,0 are dropped too."""
    cc, code = row.country, row.code.upper()
    if not code or cc in const.BETTER_ELSEWHERE or cc in const.LEFT_OUT:
        return False
    if code.startswith(const.LEFT_OUT_PREFIXES.get(cc, ())):
        return False
    if any(word in code.split() for word in const.BUSINESS_CODE_WORDS):
        return False
    if cc in const.BUSINESS_ROWS_WITHOUT_ACCURACY and not row.accuracy:
        return False
    return abs(row.lat) < 90 and abs(row.lon) <= 180 and (row.lat, row.lon) != (0.0, 0.0)


def points(rows):
    """The kept rows that place a code, in file order: exact repeats (country, code and point)
    dropped, and a code's row at a placeholder point (one PLACEHOLDER_CODES or more codes of the
    country share) when the code has a point of its own elsewhere."""
    seen, unique = set(), []
    for r in rows:
        if keep(r) and (k := (r.country, r.code, r.lat, r.lon)) not in seen:
            seen.add(k)
            unique.append(r)
    codes_at = {}
    for r in unique:
        codes_at.setdefault((r.country, r.lat, r.lon), set()).add(r.code)
    placeholder = {k for k, codes in codes_at.items() if len(codes) >= const.PLACEHOLDER_CODES}
    has_own = {(r.country, r.code) for r in unique if (r.country, r.lat, r.lon) not in placeholder}
    return [
        r
        for r in unique
        if (r.country, r.lat, r.lon) not in placeholder or (r.country, r.code) not in has_own
    ]


def reaches(rows):
    """{country: km}: REACH_FACTOR x the REACH_PERCENTILE of each distinct point's distance to its
    nearest neighbour in the same country, within REACH_MIN_KM .. REACH_MAX_KM (the ceiling for a
    country with one point)."""
    by_country = {}
    for r in rows:
        by_country.setdefault(r.country, set()).add((r.lat, r.lon))
    out = {}
    for cc, spots in by_country.items():
        if len(spots) < 2:
            out[cc] = const.REACH_MAX_KM
            continue
        lat, lon = np.array(sorted(spots)).T
        _, km = PointIndex(lat, lon).nearest(lat, lon, k=2)
        spacing = float(np.percentile(np.asarray(km).reshape(-1, 2)[:, 1], const.REACH_PERCENTILE))
        out[cc] = float(np.clip(const.REACH_FACTOR * spacing, const.REACH_MIN_KM, const.REACH_MAX_KM))
    return out


def compact(code):
    """A code without its spaces and hyphens, as people also type it ("100 00" -> "10000")."""
    return code.replace(" ", "").replace("-", "")


def postal_layer(rows, reach):
    """The `postal` point layer: id (postal:<country>:<code>, then :2, :3 ... for the code's other
    points), name (the code as written), codes (it and its compact form, for the name index only),
    place, country (alpha-2), reach_km (whole km, rounded up) and secondary (true but on a code's first
    point)."""
    count, ids, codes, secondary = {}, [], [], []
    for r in rows:
        key = (r.country, r.code)
        count[key] = count.get(key, 0) + 1
        base = f"{const.ID_PREFIX}:{r.country}:{compact(r.code)}"
        ids.append(base if count[key] == 1 else f"{base}:{count[key]}")
        codes.append("|".join(dict.fromkeys((r.code, compact(r.code)))))
        secondary.append(count[key] > 1)
    columns = {
        "id": ids,
        "name": [r.code for r in rows],
        "codes": codes,
        "place": [r.place for r in rows],
        "country": [r.country for r in rows],
        "reach_km": np.array([math.ceil(reach[r.country]) for r in rows], dtype=np.uint8),
        "secondary": np.array(secondary, dtype=bool),
    }
    types = {k: "str" for k in columns} | {"reach_km": "u1", "secondary": "bool"}
    lat = np.array([r.lat for r in rows], dtype=np.float64)
    lon = np.array([r.lon for r in rows], dtype=np.float64)
    return LayerData(const.LAYER, "point", columns, (SOURCE,), lat=lat, lon=lon, types=types)
