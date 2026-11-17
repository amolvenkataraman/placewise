"""Which rules can change an answer: an index over the rules, so `apply` runs only those.

`apply` runs every rule in order, and most rules can't touch a given answer: a point or box area
somewhere else, an id the answer doesn't mention, another country. The index finds, for one answer,
the rules that might do something; the others would return without a change, so skipping them
changes nothing, and the ones that run still run in rule order. The tests are conservative: a rule
is skipped only when it certainly does nothing.

- Areas (point + km, bbox, GeoJSON polygons, and an add rule's radius) become latitude/longitude
  boxes on a grid; a point looks up its cell. A box that wraps the antimeridian is split, and a
  circle too close to a pole, or an area too big for the grid, runs for every answer.
- Ids (rename, hide, a city rule's locality, a place area, region ids and region `id` members) run
  when the answer mentions the id, or once an earlier rule that may add a place with it has run
  (`followers`).
- Country areas run for answers in that country (rules never change an answer's country).
- Region members by code (`{"ca_cd": [...]}`) run when a place in the answer has that code.
- A GeoJSON file that can't be read when the index is built (on the first `apply`) keeps its rule
  running for every answer, so the error comes where it always did.

The index assumes well-formed answers (Place codes are dicts); it is built on the first `apply`.
"""

import math

from placewise.constants.earth import MEAN_RADIUS_KM
from placewise.model import Add, AreaSelector, CityRule, Hide, Label, RegionRule, Rename
from placewise.model.overrides import _geojson_features, _resolve

from .state import LIST_FIELDS, NEARBY_FIELDS, PLACE_FIELDS, synthetic_id

CELL_DEG = 0.1  # grid cell size: about 11 km of latitude
MAX_CELLS = 1 << 14  # an area covering more cells than this runs for every answer
_MARGIN = 1.001  # widen circles a little, so rounding can't drop a point on the edge
_EPSILON_DEG = 1e-9


def _cell(lat, lon):
    return (math.floor((lat + 90.0) / CELL_DEG), math.floor((lon + 180.0) / CELL_DEG))


def _circle_boxes(lat, lon, km):
    """Boxes holding every point within `km` (haversine) of (lat, lon), or None for "anywhere"."""
    theta = km * _MARGIN / MEAN_RADIUS_KM  # angular radius
    dlat = math.degrees(theta) + _EPSILON_DEG
    poleward = math.radians(min(abs(lat) + dlat, 90.0))
    if math.cos(poleward) <= 0:
        return None
    # hav(d) >= cos(lat1) cos(lat2) hav(dlon), and both latitudes are at most `poleward`
    ratio = math.sin(theta / 2) / math.cos(poleward)
    if ratio >= 1:
        return None
    dlon = math.degrees(2 * math.asin(ratio)) + _EPSILON_DEG
    if dlon >= 180:
        return None
    return _lon_boxes(lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def _lon_boxes(south, west, north, east):
    """(south, west, north, east) boxes, longitudes split at the antimeridian."""
    south, north = max(south, -90.0), min(north, 90.0)
    if west < -180:
        return [(south, west + 360, north, 180.0), (south, -180.0, north, east)]
    if east > 180:
        return [(south, west, north, 180.0), (south, -180.0, north, east - 360)]
    return [(south, west, north, east)]


def _area_boxes(area, base_dir):
    """Boxes an area can match in, or None for "anywhere" (also for GeoJSON that can't be read)."""
    if area.point is not None:
        return _circle_boxes(area.point.lat, area.point.lon, area.km)
    if area.bbox is not None:
        s, w, n, e = area.bbox.as_tuple()
        if w <= e:
            return [(s, w, n, e)]
        return [(s, w, n, 180.0), (s, -180.0, n, e)]
    try:
        features = _geojson_features(_resolve(area.geojson, base_dir))
    except Exception:  # the rule keeps running, and raises when it gets there, as before
        return None
    return [o.bbox.as_tuple() for f in features for o in f.outlines]


def introduced_ids(rule):
    """Ids of places a rule may put into an answer."""
    if isinstance(rule, Add):
        return {rule.id or synthetic_id(rule.origin, rule.name)}
    if isinstance(rule, Label):
        return {synthetic_id(rule.origin, v, k) for k, v in rule.fields.items() if k != "label"}
    if isinstance(rule, CityRule):
        return {synthetic_id(rule.origin, rule.city)}
    if isinstance(rule, RegionRule) and not rule.remove:
        return {rule.id}
    return set()


class RuleIndex:
    """For an answer, the indices of the entries that may change it (`candidates`, in rule order,
    plus the `followers` of each one that runs)."""

    def __init__(self, entries, handled):
        self._always = set()
        self._grid = {}  # cell -> entry indices
        self._by_id = {}  # place id -> entry indices
        self._by_country = {}  # upper-case alpha-2 -> entry indices
        self._by_code = {}  # (code key, value) -> region entry indices
        self._everything = sorted(i for i, e in enumerate(entries) if type(e.rule) in handled)
        for i in self._everything:
            self._add(i, entries[i])
        # followers[i]: later rules waiting on an id rule i may add, which run once rule i has
        self.followers = [()] * len(entries)
        for i in self._everything:
            later = {k for pid in introduced_ids(entries[i].rule) for k in self._by_id.get(pid, ()) if k > i}
            if later:
                self.followers[i] = tuple(sorted(later))

    def _on_id(self, i, pid):
        self._by_id.setdefault(pid, set()).add(i)

    def _on_boxes(self, i, boxes):
        cells = set()
        for s, w, n, e in boxes:
            (r0, c0), (r1, c1) = _cell(s, w), _cell(n, e)
            if (r1 - r0 + 1) * (c1 - c0 + 1) + len(cells) > MAX_CELLS:
                self._always.add(i)
                return
            cells.update((r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1))
        for cell in cells:
            self._grid.setdefault(cell, set()).add(i)

    def _on_area(self, i, area, base_dir):
        if area.country is not None:
            self._by_country.setdefault(area.country, set()).add(i)
        elif area.place is not None:
            self._on_id(i, area.place)
        else:
            boxes = _area_boxes(area, base_dir)
            if boxes is None:
                self._always.add(i)
            else:
                self._on_boxes(i, boxes)

    def _add(self, i, entry):
        rule = entry.rule
        if isinstance(rule, (Rename, Hide)):
            self._on_id(i, rule.id)
        elif isinstance(rule, Label):
            self._on_area(i, rule.within, entry.base_dir)
        elif isinstance(rule, CityRule):
            if rule.within is not None:
                self._on_area(i, rule.within, entry.base_dir)
            else:
                self._on_id(i, rule.locality)
        elif isinstance(rule, Add):
            if rule.within is not None:
                self._on_area(i, rule.within, entry.base_dir)
            else:
                boxes = _circle_boxes(rule.point.lat, rule.point.lon, rule.radius_m / 1000.0)
                if boxes is None:
                    self._always.add(i)
                else:
                    self._on_boxes(i, boxes)
        elif isinstance(rule, RegionRule):
            self._on_id(i, rule.id)  # removes it from an answer that has it
            if rule.remove:
                return
            for code_key, codes in rule.members.items():
                for code in codes:
                    if code_key == "id":
                        self._on_id(i, code)
                    elif isinstance(code, str):
                        self._by_code.setdefault((code_key, code), set()).add(i)
                    else:
                        self._always.add(i)
            if rule.polygon is not None:
                self._on_area(i, AreaSelector(geojson=rule.polygon), entry.base_dir)
        else:
            self._always.add(i)

    def candidates(self, result, lat, lon):
        """Indices of the entries that may change `result` at (lat, lon), in rule order."""
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):  # NaN too: no shortcuts
            return list(self._everything)
        found = set(self._always)
        if self._grid:
            found.update(self._grid.get(_cell(lat, lon), ()))
        ids, codes, all_codes = _mentioned(result)
        for pid in ids:
            if (hit := self._by_id.get(pid)) is not None:
                found |= hit
        if self._by_code:
            if not all_codes:  # a code that isn't a string: no shortcut
                found.update(i for hits in self._by_code.values() for i in hits)
            for pair in codes:
                if (hit := self._by_code.get(pair)) is not None:
                    found |= hit
        if self._by_country:
            country = result.country
            cc = country.codes.get("iso2") if country is not None else None
            if isinstance(cc, str) and (hit := self._by_country.get(cc.upper())) is not None:
                found |= hit
        return sorted(found)


def _mentioned(result):
    """(every place id in the answer, (code key, value) pairs of its admin chain places, whether
    every such value is a string)."""
    ids, codes, all_codes = set(), set(), True
    for name in PLACE_FIELDS:
        place = getattr(result, name)
        if place is not None:
            ids.add(place.id)
            for pair in (place.codes or {}).items():
                if isinstance(pair[1], str):
                    codes.add(pair)
                else:
                    all_codes = False
    for name in LIST_FIELDS:
        ids.update(p.id for p in getattr(result, name))
    ids.update(n.place.id for n in result.near)
    for name in NEARBY_FIELDS:
        if (nearby := getattr(result, name)) is not None:
            ids.add(nearby.place.id)
    return ids, codes, all_codes
