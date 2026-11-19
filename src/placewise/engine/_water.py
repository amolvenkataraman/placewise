"""Water: the sea or lake a point is on, and the sea, lake or river beside it.

Reads the `marine`, `lakes`, `reservoirs` and `rivers` layers of the first pack that has each (the
world-water pack; constants in placewise.constants.water, docs/water.md). Reservoirs (Global Dam
Watch's, where no named lake covers them) are read exactly like lakes, after them.

- On a lake: inside its outline and at least LAKE_SHORE_MARGIN_KM (per source) from its shore.
  Result.water is the lake, ON (OVER for lakes of OVER_LAKE_KM2 or more), with the distance and
  bearing to the nearest shore. Country, admin1 and city stay as on land.
- On the sea: in no country polygon, at least SEA_SHORE_MARGIN_KM from the nearest one, inside a
  marine polygon (else the one whose edge is within MARINE_SNAP_KM). Result.water is the sea, OVER,
  with the distance and bearing to the nearest coast (at any distance); the nearest country,
  which `water` held before, moves to `near` (OFFSHORE).
- Near, for points on neither: the nearest lake whose shore is within LAKE_NEAR_KM for its size,
  the nearest marine polygon within SEA_NEAR_KM and the nearest river within RIVER_NEAR_KM, each a
  NEAR entry in Result.near, with no bearing (the distance is to the feature's nearest edge).
- Label, on water: "<Over|On> [the] <name>", then the far-offshore reference ("15 km S of
  Toronto") when the point has no country; land labels are left alone.
"""

from dataclasses import dataclass

import numpy as np

from placewise.constants import lookup as lookup_const
from placewise.constants import water as const
from placewise.geo import compass, initial_bearing
from placewise.model import Nearby, Place, PlaceKind, Relation

from ._index import best_per_query

_ON = (const.MARINE, *const.LAKE_LAYERS)  # a["wet_layer"] indexes this


@dataclass(frozen=True, slots=True)
class Answer:
    """One point's water: the body it is on (or None), its Result.sources rule, and near entries."""

    on: Nearby | None
    source: str | None
    near: tuple

    def apply(self, fields, label, near, sources, has_country):
        """(label, near) with this answer folded into a Result's fields and sources (in place)."""
        extra = list(self.near)
        if self.on is not None:
            if fields["water"] is not None:  # the nearest country, far offshore
                extra.append(fields["water"])
            fields["water"] = self.on
            sources["water"] = self.source
            place = self.on.place
            text = phrase(self.on.relation, place.name, place.codes.get("type", ""))
            if not has_country and label.startswith(lookup_const.OFFSHORE_LABEL):
                text += label[len(lookup_const.OFFSHORE_LABEL) :]
            label = text
        return label, tuple(sorted((*near, *extra), key=lambda x: x.distance_km))


def phrase(relation, name, kind):
    """ "Over the North Atlantic Ocean", "Over Lake Ontario", "On Lake Tahoe"."""
    word = const.OVER_WORD if relation == Relation.OVER else const.ON_WORD
    return f"{word} {article(name, kind)}{name}"


def article(name, kind):
    """ "the " where English puts it before the name, else ""."""
    if name.lower().startswith(f"{const.THE} "):
        return ""
    if kind in const.THE_TYPES or name.endswith(const.THE_SUFFIXES) or name.startswith(const.THE_PREFIXES):
        return f"{const.THE} "
    return ""


class Water:
    def __init__(self, packs, layers):
        self.layers = layers
        self.keys = {}
        for name in const.LAYERS:
            pack = next((p for p in packs if name in p), None)
            if pack is not None:
                self.keys[name] = layers.add(pack, name, maker=_place)
        self._per_lake = {}  # (what, layer name) -> per-row array (_lake_array)

    def __bool__(self):
        return bool(self.keys)

    def layer(self, name):
        key = self.keys.get(name)
        return self.layers.layer(key) if key is not None else None

    # -- the vectorised answer ----------------------------------------------------------------------

    def answer(self, a, lat, lon, countries):
        """Fill a["wet_layer", "wet_row", "wet_km", "wet_at", "wet_snapped", "wet_near"]."""
        n = len(lat)
        a["wet_layer"], a["wet_row"] = np.full(n, -1, dtype=np.int64), np.full(n, -1, dtype=np.int64)
        a["wet_km"], a["wet_at"] = np.full(n, np.nan), np.full((n, 2), np.nan)
        a["wet_snapped"] = np.zeros(n, dtype=bool)
        self._on_lakes(a, lat, lon)
        self._on_sea(a, lat, lon, countries)
        rest = np.flatnonzero(a["wet_layer"] < 0)
        a["wet_near"] = {}
        lake_km = max(km for _, km in const.LAKE_NEAR_KM)
        searches = [(name, lake_km) for name in const.LAKE_LAYERS]
        searches += [(const.MARINE, const.SEA_NEAR_KM), (const.RIVERS, const.RIVER_NEAR_KM)]
        for name, radius in searches:
            layer = self.layer(name)
            if layer is not None and len(rest):
                limit = self._lake_array("near", name) if name in const.LAKE_LAYERS else None
                a["wet_near"][name] = _nearest_within(layer, lat, lon, rest, radius, limit)

    def _on_lakes(self, a, lat, lon):
        """On a lake, then on a reservoir for the points on neither yet."""
        for name in const.LAKE_LAYERS:
            lakes = self.layer(name)
            todo = np.flatnonzero(a["wet_layer"] < 0)
            if lakes is None or not lakes.count or not len(todo):
                continue
            found = np.atleast_1d(lakes.query(lat[todo], lon[todo])).astype(np.int64)
            hit, row = todo[found >= 0], found[found >= 0]
            if not len(hit):
                continue
            f, km, at_lat, at_lon = (np.atleast_1d(x) for x in lakes.nearest_boundary(lat[hit], lon[hit]))
            km, at = km.astype(np.float64), np.column_stack([at_lat, at_lon])
            for j in np.flatnonzero(f != row):  # another lake's shore is nearer (a lake on an island)
                km[j] = lakes.nearest_edge_km(lat[hit[j]], lon[hit[j]], row[j])
                at[j] = np.nan
            on = km >= self._lake_array("margin", name)[row]
            self._set(a, hit[on], _ON.index(name), row[on], km[on], at[on])

    def _on_sea(self, a, lat, lon, countries):
        marine = self.layer(const.MARINE)
        if marine is None or countries is None:
            return
        cand = np.flatnonzero((a["cmode"] != lookup_const.POLYGON) & (a["wet_layer"] < 0))
        if not len(cand):
            return
        km, at = a["water_km"][cand].copy(), a["water_at"][cand].copy()  # far offshore: known
        todo = np.flatnonzero(~np.isfinite(km))
        if len(todo):
            _, d, at_lat, at_lon = countries.nearest_boundary(lat[cand[todo]], lon[cand[todo]])
            km[todo], at[todo] = d, np.column_stack([at_lat, at_lon])
        keep = km >= const.SEA_SHORE_MARGIN_KM
        sea, km, at = cand[keep], km[keep], at[keep]
        row = np.atleast_1d(marine.query(lat[sea], lon[sea])).astype(np.int64)
        miss = np.flatnonzero(row < 0)
        snapped = np.zeros(len(sea), dtype=bool)
        if len(miss):
            q, f, d = marine.near_boundary(lat[sea[miss]], lon[sea[miss]], const.MARINE_SNAP_KM)
            best = best_per_query(q, d, len(miss))
            row[miss[best >= 0]] = f[best[best >= 0]]
            snapped[miss[best >= 0]] = True
        ok = row >= 0
        self._set(a, sea[ok], _ON.index(const.MARINE), row[ok], km[ok], at[ok])
        a["wet_snapped"][sea[ok]] = snapped[ok]

    @staticmethod
    def _set(a, pts, layer, row, km, at):
        a["wet_layer"][pts], a["wet_row"][pts], a["wet_km"][pts], a["wet_at"][pts] = layer, row, km, at

    def _lake_array(self, what, name):
        """Per row of lake layer `name`: its shore margin ("margin", by source), its area ("area")
        or how close its shore must be to count as near, by its area ("near"); made once."""
        key = (what, name)
        if key not in self._per_lake:
            lakes = self.layer(name)
            if what == "margin":
                sources = lakes.column("source").tolist() if "source" in lakes.fields else [""] * lakes.count
                margins = const.LAKE_SHORE_MARGIN_KM
                out = np.array(
                    [margins.get(s, const.LAKE_SHORE_MARGIN_DEFAULT_KM) for s in sources], dtype=np.float64
                )
            elif what == "area":
                has = "area_km2" in lakes.fields
                out = np.asarray(lakes.column("area_km2"), dtype=np.float64) if has else np.zeros(lakes.count)
            else:
                area = self._lake_array("area", name)
                out = np.zeros(len(area))
                for min_area, km in sorted(const.LAKE_NEAR_KM):
                    out[area >= min_area] = km
            self._per_lake[key] = out
        return self._per_lake[key]

    # -- per point, for the Results -----------------------------------------------------------------

    def rows(self, a, lat, lon):
        """An Answer per point (None where there is no water to report)."""
        n = len(lat)
        out = [None] * n
        wet, row, km = a["wet_layer"], a["wet_row"], a["wet_km"]
        on_pts = np.flatnonzero(wet >= 0)
        deg, word = np.full(n, np.nan), np.full(n, "", dtype=object)
        aimed = on_pts[np.isfinite(a["wet_at"][on_pts, 0])]
        if len(aimed):
            b = np.atleast_1d(
                initial_bearing(lat[aimed], lon[aimed], a["wet_at"][aimed, 0], a["wet_at"][aimed, 1])
            )
            deg[aimed], word[aimed] = b, np.atleast_1d(compass(b, lookup_const.COMPASS_POINTS))
        near = {}
        for name, (nrow, nkm) in a.get("wet_near", {}).items():
            key = self.keys[name]
            for i in np.flatnonzero(nrow >= 0).tolist():
                place = self.layers.place(key, int(nrow[i]))
                near.setdefault(i, []).append(Nearby(place, Relation.NEAR, float(nkm[i])))
        for i in on_pts.tolist():
            name = _ON[wet[i]]
            key, r = self.keys[name], int(row[i])
            relation = Relation.OVER
            if name in const.LAKE_LAYERS and self._lake_array("area", name)[r] < const.OVER_LAKE_KM2:
                relation = Relation.ON
            bearing = None if np.isnan(deg[i]) else float(deg[i])
            on = Nearby(self.layers.place(key, r), relation, float(km[i]), bearing, word[i] or None)
            rule = const.NEAREST if a["wet_snapped"][i] else const.POLYGON
            out[i] = Answer(on, f"{key}:{rule}", tuple(near.pop(i, ())))
        for i, entries in near.items():
            out[i] = Answer(None, None, tuple(entries))
        return out


def _nearest_within(layer, lat, lon, pts, radius_km, limit_km=None):
    """(row, km) per point (-1, inf where none): the layer's feature whose edge is nearest to each
    of `pts`, within radius_km (and within limit_km[row] when given)."""
    n = len(lat)
    rows, kms = np.full(n, -1, dtype=np.int64), np.full(n, np.inf)
    q, f, d = layer.near_boundary(lat[pts], lon[pts], radius_km)
    if limit_km is not None:
        keep = d <= limit_km[f]
        q, f, d = q[keep], f[keep], d[keep]
    best = best_per_query(q, d, len(pts))
    hit = best >= 0
    rows[pts[hit]], kms[pts[hit]] = f[best[hit]], d[best[hit]]
    return rows, kms


def _place(get, layer, row):
    codes = {k: get(k) for k in ("type", "wikidata") if get(k)}
    aliases = tuple(x for x in get("aliases").split("|") if x)
    return Place(
        get("id"), get("name") or get("id"), PlaceKind.WATER, bbox=layer.bbox(row), codes=codes,
        aliases=aliases, source=layer.sources[0] if layer.sources else None,
    )  # fmt: skip
