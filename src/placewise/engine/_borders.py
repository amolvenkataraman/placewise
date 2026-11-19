"""Country borders from the country packs: where Natural Earth's 1:10m country polygons (drawn to
~1 km) and a country pack's precise first-level units disagree, the units decide the country.

Natural Earth puts downtown Niagara Falls, New York, 600 m inside the US, in Canada: its Canada
overlaps US land along the river. The usa, can and ind packs' states and provinces (Census, StatCan,
India Post boundaries, drawn at 1:500k or finer) are where the border really is. So:

- a point inside a unit of a country pack (UNIT_LAYERS) that belongs to another country than the
  one Natural Earth gives it, or, for units clipped to the shoreline, to a country where Natural
  Earth gives none (offshore, or on no polygon: Treasure Island in San Francisco Bay), takes the
  unit's country, with that layer as its source ("usa/states:polygon"), so Result.matches says
  `within`. Admin1 and the lower levels then follow from that country as everywhere (its pack's
  counties, subdivisions or PIN areas name them), and the sea around an island is only near
  (placewise.engine._nearby.water puts on the sea only points off every country polygon);
- Natural Earth's answer stands where its own country's pack also has a unit there (two packs'
  generalised borders overlap by metres) and within BORDER_DEPTH_KM of the unit's edge (inside the
  unit's own generalisation); where two other packs both claim the point, the one it lies deeper
  inside (farther from that unit's edge) wins;
- never in a disputed area (the world pack's worldviews layer), and never from a unit flagged as
  ground only one view gives its country (the India pack's `india_view_only`): the worldview rules
  (placewise.engine._worldview) decide those exactly as before;
- a unit's country: the world admin1 carrying its id when there is one ("iso:US-PR" is Puerto
  Rico's, a country of its own in Natural Earth), none for other ISO 3166-2 ids the world pack
  doesn't know (the US territories), else the pack's country.

Cheap: one polygon query per pack layer for the points Natural Earth doesn't already place in that
layer's country, nothing more where no unit answers (almost everywhere).
"""

import numpy as np

from placewise.constants import lookup as const
from placewise.constants import naming as naming_const
from placewise.constants.worldviews import IND_VIEW_ONLY

from .naming.can import Can
from .naming.ind import Ind
from .naming.usa import Usa

# (naming rule whose pack carries the units, layer name, flag column, clipped to the shoreline).
# Only shoreline-clipped units are evidence of land where Natural Earth has none: the Census
# Bureau's cartographic boundary states (1:500k) and StatCan's cartographic boundary provinces
# leave out the sea, the bays and the Great Lakes; the India pack's states, unions of PIN-code
# areas, take in lagoons such as Chilika Lake, so they only correct a land border.
UNIT_LAYERS = (
    (Usa, naming_const.USA_STATES, None, True),
    (Can, naming_const.CAN_PROVINCES, None, True),
    (Ind, naming_const.IND_LAYERS["state"], IND_VIEW_ONLY, False),
)


class _Units:
    def __init__(self, key, layer, country, home, land):
        self.key, self.layer, self.country, self.home, self.land = key, layer, country, home, land


class Borders:
    def __init__(self, layers, admin):
        self.admin = admin
        self.units = []
        wv = admin.worldviews
        if wv is None:
            return
        for rule, name, flag, land in UNIT_LAYERS:
            pack = next((p for p in layers.packs if rule.accepts(p) and name in p), None)
            home = wv.row_of_iso2.get(rule.country, -1)
            if pack is None or home < 0:
                continue
            key = layers.add(pack, name)
            layer = layers.layer(key)
            country = self._countries(layer, home, flag)
            if (country >= 0).any():
                self.units.append(_Units(key, layer, country, home, land))

    def __bool__(self):
        return bool(self.units)

    def _countries(self, layer, home, flag):
        """Per unit, the countries row it belongs to, -1 where it is left out."""
        row_of, owner = self.admin.admin1_row_of_id, self.admin.admin1_country
        out = np.full(layer.count, home, dtype=np.int64)
        for i, uid in enumerate(layer.column("id").tolist()):
            if uid in row_of:
                out[i] = owner[row_of[uid]]
            elif uid.startswith(const.ISO_ID_PREFIX):
                out[i] = -1
        if flag is not None and flag in layer.fields:
            flagged = np.array([_truthy(v) for v in layer.column(flag).tolist()], dtype=bool)
            out[flagged] = -1
        return out

    def answer(self, a, lat, lon):
        """Correct a["cidx"], a["cmode"] in place; a["csrc"]: per point, the unit layer's source
        where a unit decided the country (else None), or None when no unit decided any."""
        n = len(lat)
        a["csrc"] = None
        if not self.units:
            return
        cidx, cmode, area = a["cidx"], a["cmode"], a["area"]
        on_polygon = cmode == const.POLYGON
        open_ = area < 0  # outside every disputed area, as Natural Earth places the point
        found = []  # (points, unit index, rows) per layer: units that correct the country
        own = np.full(n, False)  # on a Natural Earth polygon and in a unit of that country
        for u, units in enumerate(self.units):
            ask = (cidx != units.home) | ~on_polygon if units.land else (cidx != units.home) & on_polygon
            pts = np.flatnonzero(open_ & ask)
            if not len(pts):
                continue
            rows = np.atleast_1d(units.layer.query(lat[pts], lon[pts])).astype(np.int64)
            hit = rows >= 0
            pts, rows = pts[hit], rows[hit]
            country = units.country[rows]
            agrees = (country == cidx[pts]) & on_polygon[pts]  # Puerto Rico's unit in Puerto Rico
            own[pts[agrees]] = True
            corrects = (country >= 0) & ~agrees  # another country, or land where NE has none
            if corrects.any():
                found.append((pts[corrects], u, rows[corrects]))
        if not found:
            return
        self._own_layers(a, lat, lon, found, own)
        best = {}  # point -> (depth, unit, row): the unit correcting it, at least BORDER_DEPTH_KM in
        for pts, u, rows in found:
            keep = ~own[pts]
            for p, r in zip(pts[keep].tolist(), rows[keep].tolist(), strict=True):
                depth = float(self.units[u].layer.nearest_edge_km(lat[p], lon[p], r))
                if depth >= const.BORDER_DEPTH_KM and (p not in best or depth > best[p][0]):
                    best[p] = (depth, u, r)  # two packs claim it: the unit it lies deeper inside
        if not best:
            return
        pts = np.fromiter(best, dtype=np.int64, count=len(best))
        pts = pts[self._undisputed(a, lat, lon, pts)]
        if len(pts):
            a["csrc"] = np.full(n, None, dtype=object)
        for p in pts.tolist():
            _, u, r = best[p]
            units = self.units[u]
            cidx[p], cmode[p] = units.country[r], const.POLYGON
            a["csrc"][p] = f"{units.key}:{const.POLYGON}"

    def _own_layers(self, a, lat, lon, found, own):
        """Mark in `own` the claimed points that their Natural Earth country's own pack also has a
        unit at (generalised borders overlapping): Natural Earth's answer stands there."""
        claimed = np.unique(np.concatenate([pts for pts, _, _ in found]))
        cidx, on_polygon = a["cidx"], a["cmode"] == const.POLYGON
        for units in self.units:
            pts = claimed[(cidx[claimed] == units.home) & on_polygon[claimed] & ~own[claimed]]
            if len(pts):
                rows = np.atleast_1d(units.layer.query(lat[pts], lon[pts])).astype(np.int64)
                inside = rows >= 0
                own[pts[inside]] = units.country[rows[inside]] == units.home

    def _undisputed(self, a, lat, lon, pts):
        """Per point of `pts`: in no disputed area. Points Natural Earth put on a country polygon
        were tested already; the rest (offshore, or on no polygon) are tested here."""
        ok = np.ones(len(pts), dtype=bool)
        areas = self.admin.areas
        test = np.flatnonzero(a["cmode"][pts] != const.POLYGON)
        if areas is not None and len(test):
            ok[test] = np.atleast_1d(areas.query(lat[pts[test]], lon[pts[test]])) < 0
        return ok


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no")
    return bool(value)
